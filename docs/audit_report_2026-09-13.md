# FinRisk-Agent 深度审计报告

- 审计日期：2026-09-13
- 审计对象：`C:\Document\Finrisk\financial-risk-agent`（HEAD `6688c0f`，与 GitHub 线上一致）
- 范围：跨文件传输契约、前端渲染稳健性、后端公式正确性、代码错误
- 方法：全量通读 + 可执行验证（ruff / pytest+覆盖率 / tsc / next build / 端点直调 / 端到端代理复现 / 文献数值回归）

> 本文件为审计新增的未跟踪文件，不修改任何既有代码。

---

## 0. 结论摘要

| 级别 | 数量 | 概述 |
|---|---|---|
| P0 严重 | 4 | 代理 content-length 错误导致所有错误响应失真；`/assess` 可被触发 500；前端无错误边界；**XBRL 解析把上一年度比较数当作本年度数** |
| P1 重要 | 14 | 响应零校验且无超时；试点表覆盖率列取错数据源；6 个组件存在无防护崩溃路径；25/68 规则永不触发；失败状态误判；企业层 3 个领域取值永远无法结案；策略阈值契约缺口（500 / 失败开放）；**LLM 异常元组漏 `IndexError`/`AttributeError` 绕过重试与成本日志**；**`parse_number` 丢弃"千分位+小数"**；**`_SCALE_PATTERN` 把正文 `000` 当"千"→ 1000× 错误**；**`selective_metrics` 把未知排成最安全**；**消融实验为算术代理 + 2 个硬编码指标**；**6 个脚本无 `__main__` 守卫（import 即改写产物 / 挂起 90 秒）**；**已提交示例报告与当前代码输出不一致（Moderate → Low）** |
| P2 一般 | 33 | 格式化/键值/输入控件/类型声明/状态机/并发/可观测性/FCF 符号约定/别名表分歧/覆盖率盲区等局部缺陷 |

**工程门禁全部通过**（ruff 无告警、pytest 208 passed / 2 skipped、覆盖率 92%、`tsc --noEmit` 通过、`next build` 成功）。**财务模型与评估指标的公式经独立核算未发现错误。**

**关键交叉证据**：本报告确认的绝大多数缺陷，**恰好落在单元测试未覆盖的行上**（见 J3）。覆盖率缺口即缺陷藏身处 —— 因此修复缺陷时应同步补测试，否则同类缺陷会再次溜过门禁。

> 章节 H 为 2026-09-13 追加的企业层（`backend/finrisk/enterprise/`）深度审计，含 SQL 迁移契约、鉴权、状态机与并发。企业层的**表结构与迁移契约逐列核对无误**，缺陷集中在**词表可达性、策略校验与失败开放语义**。
>
> 章节 I 为同一日追加的**研究层**（XBRL / LLM / 归一化 / 统计基准）审计；章节 J 为**脚本、测试与迁移契约**审计。研究层最严重的发现是 I1：`parse_companyfacts` 的结果**取决于 SEC JSON 的条目顺序**，会把比较期数据当作当期数据。

---

## A. 跨文件传输问题

### A1 【P0】代理转发上游 `content-length`，导致所有非 2xx 响应被截断

**位置**：`frontend/app/api/v1/[...path]/route.ts:82-91`

```ts
const responseHeaders = new Headers();
for (const name of FORWARDED_RESPONSE_HEADERS) {   // 含 "content-length"
  const value = response.headers.get(name);
  if (value) responseHeaders.set(name, value);
}
if (!response.ok) {
  return NextResponse.json({ detail: "upstream error" }, { status: response.status, headers: responseHeaders });
}
```

错误分支把**上游原始响应体的** `content-length` 原样转发，但 body 已被替换为 `{"detail":"upstream error"}`（27 字节）。

**端到端复现证据**（模拟上游返回 401 + 84 字节 JSON，经 `next start` 代理）：

```
上游直连:   Content-Length: 84   body = {"detail": "validation failed: ..."}
经 Next 代理: content-length: 84   body = {"detail":"upstream error"}
curl: (18) end of response with 57 bytes missing      # 84 - 27 = 57
```

**影响链**：
1. 浏览器把长度不符的响应当作网络层错误（`Failed to fetch` / `ERR_CONTENT_LENGTH_MISMATCH`），而非可解析的 401/422/429；
2. `lib/api.ts` 的 `catch` 分支被触发 → `upstreamUnavailable: true`；
3. 于是**401 密钥错误、429 限流、422 校验失败全部被显示为"上游不可用"**，真实原因永远不呈现；
4. `errorIsUpstream === true` 还会错误地渲染"改用内置样本"按钮。

这直接违反了 `lib/api.ts` 顶部自己声明的契约：*"Validation, auth and server errors are surfaced as failures, never silently replaced with sample data."*

**修复建议**：从 `FORWARDED_RESPONSE_HEADERS` 移除 `content-length`（框架会自行计算）；或错误分支改用 `new NextResponse(body, { status, headers })`。

---

### A2 【P1】公开试点表的"Evidence coverage"列对每家公司都是错的

**位置**：`backend/finrisk/api.py:327`

```python
"coverage": full_hybrid["evidence_coverage"],   # 数据集级均值，非逐公司值
```

**证据**（直接调用端点 + 比对源数据）：

```
返回给前端: Apple 0.5833 / Microsoft 0.5833 / Intel 0.5833   ← 三行完全相同
predictions.csv 真实值: aapl-2024 0.65 / msft-2024 0.45 / intc-2024 0.65
(0.65 + 0.45 + 0.65) / 3 = 0.58333...   ← 与返回值吻合
```

根因：`research/results/public_v1/summary.json` 的 `decompositions` 数组本身**不含**逐公司覆盖率，实现者只能取到 `summaries` 里的聚合值；而真正的逐公司值在 `predictions.csv` 的 `evidence_coverage` 列，可用 `example_id` 关联。

**影响**：Workbench 首屏表格里一整列数字对每一行都不正确。离线样本 `lib/demoFixture.ts` 也复制了同样的 0.5833，所以线上/离线两条路径都错。

**修复建议**：按 `example_id` 从 `predictions.csv` 取 `baseline == "full_hybrid"` 行的 `evidence_coverage`。

---

### A3 【P2】前端类型声明与后端实际返回不符

**位置**：`frontend/lib/types.ts:218` vs `backend/finrisk/agent/review.py:68`

```ts
// types.ts
analyst?: { status?: string; checked_claims?: number };   // 声明为对象
```

```python
# review.py
"analyst": [asdict(item) for item in judgements],          # 实际是数组
```

当前无任何组件读取 `role_review.analyst`，属潜伏的类型契约错误（若将来使用会静默取到 `undefined`）。

**其余契约核对结果**：`AssessmentPayload`、`AgentPayload`、`DecisionTrace`、`DecisionPath`、`FusionResult`、`Epistemics`、`FailureState`、`Conclusion`、`ComponentTelemetry`、`PilotPayload` 与后端 dataclass / dict 输出**逐字段一致**；`DecisionReasonCode` 的 8 个枚举值与前端 `REASON_COPY` 的 8 条文案**一一对应**；`severity.py` 的 20/40/60/80 分档与前端 `severity-*` / `band-*` CSS 类**完全对应**。

---

## B. 前端渲染与稳健性

### B1 【P0】没有任何错误边界，任一子组件抛错即整页空白

`frontend/app/` 下无 `error.tsx` / `global-error.tsx`，全仓库无 `ErrorBoundary`。React 在渲染期抛错时会卸载整棵子树，用户看到完全空白页面。结合 B2（响应零校验），触发概率被显著放大。

**修复建议**：新增 `app/error.tsx`（App Router 约定）并在 `page.tsx` 的分析结果区包一层组件级边界。

### B2 【P1】`analyzeDocument` 不做响应形状校验，也没有超时

**位置**：`frontend/lib/api.ts:129-172`

与同文件的 `loadPilot` 形成明显不对称：

| | `loadPilot` | `analyzeDocument` |
|---|---|---|
| 形状守卫 | 有（`isPilotPayload`） | **无**，直接 `payload as AssessmentPayload` |
| 超时 | `AbortSignal.timeout(8000)` | **无** |

后果：HTTP 200 但形状异常（HTML 错误页、`{}`）会被当作成功载荷交给组件 → 命中 B3 的崩溃路径；上游挂起则 `loadingAnalysis` 永远为 `true`，按钮永久禁用。

### B3 【P1】6 个组件共 20+ 处无防护属性访问（崩溃路径）

均为「后端字段缺失或改名 → 渲染期 TypeError → 因 B1 而整页空白」：

| 文件 | 行 | 表达式 |
|---|---|---|
| `WhyDecision.tsx` | 53 | `payload.evidence_coverage.toFixed(3)` |
| | 150 | `payload.missing_information.length` |
| | 166 | `Object.entries(payload.confidence_components)` |
| | 172 | `value.toFixed(2)` |
| `EvidenceTrail.tsx` | 14 | `item.verification_status.toUpperCase()` |
| | 19 | `item.confidence.toFixed(2)` |
| | 67 | `conclusion.evidence.length` |
| `DimensionGrid.tsx` | 29 | `Object.entries(dimensions)` |
| | 53 | `dimension.coverage.toFixed(2)` |
| | 56 | `dimension.key_drivers.length` |
| `DecisionPaths.tsx` | 24 | `trace.paths.length` |
| | 78 | `Object.entries(path.input_provenance)` |
| | 90 | `path.fusion_contribution.role` |
| | 108 | `path.rule_version.slice(0, 16)` |
| | 122 | `node.replace(/_/g, " ")` |
| | 157 | `path.source_evidence.length` |
| `AgentTrace.tsx` | 26 / 33 | `trace.map` / `plan.map` |
| | 50 | `status.toLowerCase()` |
| `TelemetryPanel.tsx` | 16 / 17 | `items.reduce(...)` |
| | 78 | `item.latency_ms.toLocaleString()` |

**注**：`WhyDecision` 位于默认打开的 overview 标签页，风险最高。后端 `enterprise/decision.py:74-79` 已为其中一个点打过补丁，注释直言 *"an undefined value crashed the Decision paths tab"* —— 说明这是已知脆弱面，但修复方式是在服务端保留空键，客户端至今不设防。

**修复建议**：在 `lib/api.ts` 加一个与 `isPilotPayload` 同级的 `isAssessmentPayload` 守卫（纵深防御），并把上述访问改为可选链 + 兜底文案。

### B4 【P2】渲染细节缺陷

| 位置 | 问题 |
|---|---|
| `DecisionSummary.tsx:40` | `overall_score === null` 未覆盖 `undefined` → 缺值时显示 `N/A/100` |
| `DimensionGrid.tsx:14,35` | `band(undefined)` 落到 `"very_low"` 而非 `"none"`；`unknown` 判定漏 `undefined` → 渲染空 `<b>` + `/100` |
| `PilotTable.tsx:43` | `` `annotation: ${payload.annotation_status}` ``，而 `isPilotPayload` 不校验该字段 → 缺字段时显示字面量 `annotation: undefined` |
| `PilotTable.tsx:61` | `key={row.entity}`；当前一公司一年不冲突，换多年数据即重复 key |
| `page.tsx:229` | `agent?.component_telemetry ?` 对空数组为真（其他标签页用 `.length`），判断方式不一致 |
| `presentation.mjs:2` | `displayScore` 直接 `String(score)` 不做四舍五入，而 `DecisionSummary.ratio` 用 `toFixed(3)`；风险指数可能显示浮点尾数 |
| `presentation.mjs:15` | `evidence.page ? ...`，`page === 0` 被当作缺失（后端 `FinancialValue.page` 默认值正是 0） |
| `IntakePanel.tsx:85` | 数字输入 `Number("") === 0`：清空年份框会强制变为 `0`，而 `min=1900` 使表单无法提交，用户被卡住 |
| `next.config.ts:24` | CSP `script-src` 缺 `'unsafe-eval'`，`next dev` 的 HMR 会被拦截（仅影响开发模式，生产无碍） |

---

## C. 后端公式与数值正确性

### C1 财务模型公式：经独立核算，未发现错误

用独立参考实现与手工核算做数值回归：

```
Ohlson O-Score   = -1.7347    (文献算例参考 -1.7347)      ✅
Ohlson 概率      = 0.149983   (文献算例参考 0.149983)     ✅
Altman Z         = 3.3368     (手工核算 3.3368)           ✅
```

逐项核对结论：

- **Altman**：Z / Z' / Z'' 三变体的系数、分母、阈值（1.81/2.99、1.23/2.90、4.15/5.85）与原始文献一致；`X4` 按变体正确切换市值/账面权益；Z'' 正确省略资产周转项；金融机构被显式排除。
- **Beneish M**：8 变量定义与符号全部正确（DSRI/GMI/AQI/SGI/DEPI/SGAI/TATA/LVGI），`GMI` 为"前期毛利率 ÷ 当期毛利率"方向正确，阈值 -1.78 正确。
- **Piotroski F**：9 个二值信号与文献一致；分母使用期末而非期初资产，已在 `interpretation` 与 `formula` 中明确标注为 proxy 局限。
- **Ohlson O**：9 因子系数逐一核对，**`OENEG` 取 -1.72、`INTWO` 取 +0.285** 与 Ohlson(1980) Model 1 一致（这两个符号极易写错，此处正确）；`SIZE = ln(TA/GNP指数)` 正确；`CHIN` 分母为 0 时置 0 属合理降级。
- `_logistic` 对 `x <= -700` 做饱和处理，避免 `math.exp` 溢出——注释记录的正是曾经导致 500 的真实缺陷。

### C2 评估指标公式：未发现错误

`evaluation.py` 逐项核对：precision/recall/F1、混淆矩阵、balanced accuracy（各类召回均值）、Brier、ROC-AUC（并列计 0.5）、ECE（分箱含 `c == 1` 边界）、average precision（**按分数分组处理并列**，注释记录了此前 `sorted(zip(...))` 导致常数评分基线 AUPRC=1.0 的缺陷）。所有除法均有零分母防护。

### C3 【P1】68 条规则中 25 条永远不会触发

`rules.py:63-76` 的 `unproducible_rule_conditions()` 返回 25 个 `(rule_id, metric)`，即条件引用的 fact 在整个代码库中没有任何产出方：

```
restatement_detected / adverse_audit_opinion / qualified_audit_opinion / auditor_change
auditor_resignation / covenant_breach / board_independence_low / internal_control_ineffective
ceo_cfo_turnover / related_party_material / related_party_growth / customer_concentration
supplier_concentration / material_litigation / regulatory_investigation / late_filing
accrual_ratio / non_gaap_adjustment_ratio / auditor_adjustment / demand_weakness
debt_due_12m_ratio / floating_rate_debt_ratio / unused_facility_ratio
debt_maturity_concentration / free_cash_flow_negative_years
```

受影响规则 **25 / 68（37%）**，涵盖 ACC_002~008、BUS_002~008、CFL_008、GOV_001~002 等。这些是治理/审计/披露类事实，抽取器并不产出。

`rules.py` 的 docstring 承认"存在此类规则"，但未量化；实际比例达 37%，意味着规则引擎的声明覆盖面与有效覆盖面存在系统性差距。

### C4 【P2】`evidence_quality` 与 `confidence` 同值

`pipeline.py:318` 与 `orchestrator.py:311` 均设 `evidence_quality = confidence`。项目在 `scoring.py:39-42` 明确声明"证据覆盖 ≠ 证据质量"，但 `Assessment` 里两个字段恒等，`confidence_components` 的权重合成结果被同时当作两个概念发布。属设计取舍，但与文档强调的区分不完全自洽。

---

## D. 代码错误

### D1 【P0】`/api/v1/assess` 可被触发未捕获 `StopIteration` → HTTP 500

**位置**：`backend/finrisk/pipeline.py:215`

```python
model = next(m for m in models if m.name == mapping["model"])
```

`models` 仅在提供 `previous` 时才包含 Beneish / Piotroski，而 `facts = {metric.value ...} | current` 会把**调用方传入的同名键**当作真值。因此只要请求体里带上模型指标名并跨过阈值，就会 `StopIteration`。

**复现**（`POST /api/v1/assess` 的 `current` 是自由 dict，仅校验有限性与布尔合法性，无键白名单）：

```
current={'...': ..., 'beneish_m_score': 0.5},  无 previous
→ RAISED StopIteration
current={'...': ..., 'piotroski_f_score': 2.0}, 无 previous
→ RAISED StopIteration
```

`api.py:359` 的 `assess()` **只捕获 `ValueError`**，所以异常逃逸到 `correlation_middleware`，被兜底为 `500 {"detail":"internal server error"}`——应为 422 校验错误。

**对比**：Agent 路径（`orchestrator.py:459`）用 `except Exception` 兜底，会降级为 422，所以只有 `/api/v1/assess` 与 `/api/v1/agent/assess` 的确定性分支受影响。

**修复建议**：`next(..., None)` 后跳过并记告警；同时对 `AssessmentRequest.current` 增加键白名单校验。

### D2 【P1】`llm_unavailable` 失败状态语义错误

**位置**：`orchestrator.py:199`

```python
"llm_unavailable": bool(pages and not claims),
```

`claims` 来自 `extraction["accepted"]`，即**已通过引文验证的**声明子集。若 provider 正常工作、抽取到声明、但没有任何声明通过验证，`claims == []` 成立 → 被误判为"LLM 不可用"。

**影响**：`failure_aware_decision` 会把该场景当作 review 级失败，把决定降级为 `REVIEW`，并在 `failure_state.review_failures` 里记录 `llm_unavailable`——理由与事实不符（真实原因是证据未通过验证，而非 provider 故障）。同时前端 `FAILURE_COPY.llm_unavailable` 会显示"The narrative provider failed"，属误导性文案。

**修复建议**：改用已存在的准确标志 `semantic_failed`。

### D3 【P2】其它

| 位置 | 问题 |
|---|---|
| `orchestrator.py:269-272` | 模型名映射的 `else` 分支把任何未知模型归为 `"Ohlson O-Score"`，可能错标 applicability |
| `orchestrator.py:246-248` | `evidence_paths = {path["reason_code"]: path ...}` 用 dict 收敛，若两条 path 共享 reason_code 会丢一条（当前不可达） |
| `orchestrator.py:285-297` | 注释宣称 critic 可在 `PASS < FLAG < REVIEW < ABSTAIN` 上单向收紧，但代码只处理 `recommended == "REVIEW"`。经核 `review.py:71` 只会返回 `REVIEW`/`UNCHANGED`，故**当前无缺陷**，属注释与实现范围不一致 |
| `normalization.py:parse_number` | 欧洲式 `1.234,56`（同时含千分位点与小数逗号）解析为 `None`（失败安全，非错误，但未支持） |
| `evaluation.py:42,74` | `roc_auc` / `confusion_matrix` 未校验长度一致，`zip` 会静默截断（其它函数均有校验） |

---

## E. 已验证无问题（避免误伤）

- **财务模型与评估指标公式**：见 C1、C2，含文献数值回归。
- **`metrics.py`**：`_safe_div` 同时防护零分母与溢出为 `inf`；`None` 表示"缺失"的语义贯彻一致；`*_growth` 在前期为负或为 0 时置 `None`（避免两次亏损被读成"增长"）；DSO/DIO/DPO/CCC 公式正确；`ebit` 回退 `operating_income` 逻辑正确。
- **`severity.py`**：20/40/60/80 单一来源，同时供给人类标签与机器键，前端 CSS 类完全对齐。
- **`fusion.py`**：`hierarchical_escalation` 的非补偿性下限确实单调（增加不利维度不会降低分数）；`interaction_aware` 把 `None` 与 0 严格区分（缺失不等于安全）；`failure_aware_decision` 的 `DISPOSITION_RANK` 单调收紧正确；`deduplicate_contributions` 按维度而非全局去重，避免"增加证据反而降分"。
- **代理安全加固**：方法白名单（GET/POST）、路径穿越与编码分隔符拒绝、云元数据地址与 link-local 拒绝、`FINRISK_API_ALLOWED_HOSTS` 允许列表、请求头白名单（不再转发 cookie/authorization）、`redirect: "manual"`、10s 超时。
- **`evidence.py` / `verification.py`**：`PROOF_COVERED_STATUSES` 与 `PROOF_STATUSES` 的区分有明确注释支撑，`located` 刻意不算通过证明门。
- **离线样本**：`lib/demoFixture.ts` 含全部组件所需字段（已逐项核对）。
- **工程门禁**：`ruff check backend tests scripts` → All checks passed；`pytest` → **208 passed / 2 skipped**（跳过的是需 PostgreSQL 的用例）；覆盖率 **92%**（阈值 90%）；`tsc --noEmit` 通过；`next build` 成功。
- **仓库状态**：审计未修改任何受版本控制的文件，`git status` 干净。

---

## F. 建议修复优先级

1. **A1** 代理 content-length —— 一处改动即可让全部错误路径恢复真实语义，收益最高。
2. **B1 + B2 + B3** 错误边界 + 响应校验守卫 —— 三者组合才能把"整页空白"变成"局部降级"。
3. **I1** `parse_companyfacts` 比较期错配 —— **最严重的数据正确性问题**：同一份 SEC 文件，仅条目顺序不同就会在 FY2023 / FY2022 之间翻转，且静默标记 `restated=True`。修复可直接照搬仓库内 `sec_bulk.py` 的 `accn` + `end` 锚定做法，并补一条含比较期的 XBRL 夹具。
4. **D1** `StopIteration` → 422 —— 明确的输入校验缺口。
5. **H2** 策略阈值校验 + `risk_direction` 失败开放 —— **静默把 critical 判成 within_appetite**，是本次审计中风险语义最严重的一条；同时修掉可达的 500。
6. **H1** `RiskDomain` 3 个取值不可达 —— 三处业务能力实际不可用，且 `service.py` 与 `api.py` 重复实现同一门禁（应抽公共函数）。
7. **H7** `transition` 丢失更新 —— 加 `FOR UPDATE` 或乐观锁，否则状态机在并发下形同虚设。
8. **J1 + J2** 给 6 个脚本补 `__main__` 守卫，并**重新生成 `examples/intel_2024_sample_report.{txt,pdf}`** —— 当前已提交示例显示 42.7/Moderate，代码实际产出 39.1/Low，属对外可见的事实性偏差。
9. **I3 + I4** `parse_number` 与 `_SCALE_PATTERN` —— 前者静默丢弃最常见的"千分位+小数"写法，后者产生 1000× 错误；两者都直接污染下游所有比率与模型输入。
10. **A2** 试点表覆盖率 —— 公开数据正确性问题，影响对外呈现。
11. **I5** `selective_metrics` 未知样本排序 —— 选择性预测指标方向性错误，会使任何"选择性评估"结论失真。
12. **D2** `llm_unavailable` 语义 —— 影响决定理由的可信度。
13. **I2** LLM 异常元组补齐 `IndexError` / `AttributeError` —— 否则结构退化的响应会绕过重试与成本日志。
14. **I6** 消融实验与硬编码指标 —— 需产品决策：改为真实重跑，或在文档中明确标注为算术代理。
15. **H5** `traced_stage` 误报"完成" + 日志脱敏绕过 —— 影响可观测性与敏感信息边界。
16. **H3** `FINRISK_ENV` 归一化统一 —— 一行改动即可堵住"生产环境静默退化为内存存储"。
17. **J4** 前端补测试 —— 至少覆盖 `api.ts` 的形状守卫与 `[...path]/route.ts` 的错误路径；这是让前端"不容易出问题"的唯一可持续手段。
18. **C3 / H9** 死规则与越界原因码 —— 需产品决策：补齐产出方，或从词表/规则集中移除并在文档中披露有效覆盖面。
19. **J5** 7 张空壳表 —— 需产品决策：补齐持久化，或从迁移中移除并在文档中澄清"仅内存实现"。
20. **I9 / I12** FCF 符号约定与 XBRL 别名表 —— 统一到 `metrics.py` 的 `abs()` 约定与单一别名来源。
21. **H4 / H6 / H8 / H10 / I7 / I8 / I10 / I11 / I13** —— 潜伏缺陷与不一致，建议随相关模块改动一并修正。
22. **补测试策略**：凡修复上述任一条，**必须同时在 J3 表中对应的未覆盖行上补一条测试** —— 否则门禁（92% 覆盖率）仍会放过同类缺陷。

---

## G. 复现方式

```bash
# 依赖（均在项目内，.venv/ 与 frontend/node_modules 已被 .gitignore 覆盖）
python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -c requirements.lock -e ".[dev]"
cd frontend && npm ci

# 后端门禁
./.venv/Scripts/python.exe -m ruff check backend tests scripts
./.venv/Scripts/python.exe -m pytest --cov=finrisk --cov-report=term-missing

# 前端门禁
cd frontend && npx tsc --noEmit && npx next build && node --test test/*.test.mjs

# D1 复现
./.venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'backend');\
from pathlib import Path;from finrisk.pipeline import FinRiskPipeline;\
p=FinRiskPipeline(Path('.'));\
p.assess('X',2024,{'revenue':1000.0,'net_income':50.0,'total_assets':2000.0,\
'current_assets':500.0,'current_liabilities':300.0,'total_liabilities':1200.0,\
'shareholder_equity':800.0,'operating_income':80.0,'operating_cash_flow':90.0,\
'cash':100.0,'beneish_m_score':0.5},None,{})"   # → StopIteration

# A2 复现
./.venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'backend');\
from finrisk.api import public_pilot;print(public_pilot()['rows'])"

# I1 复现：把同一份 companyfacts 的条目顺序颠倒，观察 FY 归属翻转
./.venv/Scripts/python.exe -c "import sys,json;sys.path.insert(0,'backend');\
from finrisk.xbrl import parse_companyfacts;\
cf=json.load(open('research/<aapl_companyfacts>.json'));\
a=parse_companyfacts(cf,[2023]);\
cf['facts']['us-gaap']['RevenueFromContractWithCustomerExcludingAssessedTax']['units']['USD']\
 .reverse();\
b=parse_companyfacts(cf,[2023]);\
print(a[0].value, b[0].value)"   # → 394328000000 383285000000（同一文件！）

# I2 复现：结构退化的上游响应绕过重试与调用日志
./.venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'backend');\
from finrisk.llm import StructuredLLMProvider;\
p=StructuredLLMProvider(model='m',endpoint='http://127.0.0.1:1/v1',max_retries=3);\
p._content=lambda *a,**k: {'choices': []};\
import traceback;\
try: p.extract({1:'x'},'doc',2024)\
except Exception as e: print(type(e).__name__, 'call_logs=', len(p.call_logs))"   # → IndexError call_logs= 0

# I3 复现
./.venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'backend');\
from finrisk.normalization import parse_number;\
print([parse_number(x) for x in ['1,234.56','12,345.6','(1,234.56)','1,234']])"   # → [None, None, None, 1234.0]

# I4 复现
./.venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'backend');\
from finrisk.parser import _SCALE_PATTERN;\
print(_SCALE_PATTERN.search('Revenues increased to \$1,000,000 in 2023').group())"   # → 000

# I5 复现
./.venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'backend');\
from finrisk.benchmark_protocol import selective_metrics;\
print(selective_metrics([1,0,1,0],[0.9,0.1,None,0.05]))"   # → risk_ranking 把 None 排最后

# J1 复现（会覆写 examples/ 下两个已跟踪文件，请先备份或事后 git checkout --）
./.venv/Scripts/python.exe -c "import importlib.util,sys;\
spec=importlib.util.spec_from_file_location('g','scripts/generate_public_sample.py');\
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)"   # → 覆写示例产物
git diff --stat examples/   # → 42.7/Moderate 变为 39.1/Low
git checkout -- examples/intel_2024_sample_report.txt examples/intel_2024_sample_report.pdf

# A1 复现：启动一个返回长错误体的假上游，再经 next start 代理请求
```

---

## H. 企业层（`backend/finrisk/enterprise/`）深度审计

审计范围：`api.py`(489) `fusion.py`(388) `service.py`(251) `domain.py`(196) `decision.py`(182) `security.py`(170) `postgres.py`(146) `governance.py`(134) `repository.py`(127) `temporal.py`(123) `applicability.py`(104) `decision_bundle.py`(92) `workflow.py`(87) `observability.py`(77) `scenario.py`(73) `evidence_graph.py`(72) `telemetry.py`(61) `calibration.py`(61) `tension.py`(59) `storage.py`(54) `jobs.py`(50) `policy.py`(42) `integrity.py`(41) `portfolio.py`(32) `auth.py`(18) `alerts.py`(17)。

### H1 【P1】`RiskDomain` 有 3 个取值永远无法通过 ACCEPTED/RESOLVED 门禁

`service.py:110-147`（以及 `api.py:252-297` 的**逐字重复实现**）在流转到 `ACCEPTED`/`RESOLVED` 时要求 decision_trace 中存在同时满足以下三条件的路径：

1. `evidence_path_status == "VERIFIED"`
2. `source_evidence` 非空
3. `aliases.get(risk_domain, risk_domain) == case.domain.value`

而 `risk_domain` 只有两个产生源，两者取值集合**完全相同**：

| 产生源 | 取值集合 |
|---|---|
| `decision.py:22` 遍历 `assessment["dimensions"]` 的键 | `scoring.CATEGORIES` 的 8 个键 |
| `decision.py:72` `contradiction["category"]` = `claim.risk_category` | `llm.ALLOWED_CATEGORIES`（经核实与 `CATEGORIES` **完全一致**，8 项） |

即 `risk_domain` 恒属于 `{liquidity, solvency_leverage, profitability, cash_flow, earnings_quality, accounting, governance_audit, business_going_concern}`；经 `service.py` 的 alias 映射后为 `{liquidity, solvency_leverage, profitability, cash_flow, earnings_quality, accounting_anomaly, governance_audit, business_going_concern}`。

**不在其中的 `RiskDomain` 取值：**

| 枚举成员 | 取值 | 后果 |
|---|---|---|
| `RiskDomain.COVENANT` | `covenant_refinancing` | 该类案件永远无法流转到 ACCEPTED/RESOLVED |
| `RiskDomain.COUNTERPARTY` | `counterparty_concentration` | 同上 |
| `RiskDomain.DISCLOSURE_TENSION` | `disclosure_tension` | 同上 |

调用方只会得到 `ValueError("a verified server-side evidence path is required")`，错误信息完全不指向真实原因（词表不可达）。

补充发现：

- `decision.py:72` 的默认值 `"disclosure_tension"` 是**死代码**：`Contradiction.category` 是 dataclass 首字段，`asdict()` 后必然存在，`.get(key, default)` 的默认值永不生效。
- `service.py:120-125` 的 alias 表中 `"governance"` / `"going_concern"` / `"solvency"` 三个键是**死条目**（真实维度键已是全名 `governance_audit` 等），仅 `"accounting" → "accounting_anomaly"` 生效。
- `covenant_refinancing` / `counterparty_concentration` 在整个仓库中**仅出现于 `enterprise/domain.py`**，无任何产出方。

**实证**：以 `research/benchmark/public_company_observations.json` 的 3 个样本跑真实 `FinRiskPipeline` + `build_decision_trace`，观测到的 `risk_domain` 仅 `{cash_flow, liquidity, profitability, solvency_leverage}` —— 全部落在上述 8 值集合内，无越界值。

```bash
./.venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'backend');import json,pathlib;\
from finrisk.pipeline import FinRiskPipeline;from finrisk.enterprise.decision import build_decision_trace;\
obs=json.loads(pathlib.Path('research/benchmark/public_company_observations.json').read_text());\
p=FinRiskPipeline();\
[print(e['company'],sorted({x['risk_domain'] for x in build_decision_trace(\
p.assess(e['company'],e.get('year',2023),e['current'],e.get('previous')).to_dict(),\
{'decision':'REVIEW','disagreement':0.0,'drivers':[],'method':'m','reason_codes':[]})['paths']})) for e in obs['examples']]"
```

### H2 【P1】策略阈值契约缺口：不校验即落库，读取时崩溃或静默失效

`PolicyCreate.thresholds` 声明为 `dict[str, dict[str, float | str]]`（`api.py:121-124`），只校验**形状**；`service.py:66-88` 原样落库；`policy.py:6-42` 读取时**假定语义**。经 API 自身的 Pydantic 模型实证，以下载荷**全部被接受**：

| 载荷 | `evaluate_kri` 结果（value=0.95, critical=0.6） |
|---|---|
| `{"debt":{"warning":"low","critical":"high"}}` | `TypeError: '>=' not supported between instances of 'float' and 'str'` |
| `{"debt":{...,"risk_direction":"HIGH"}}` | `within_appetite`（**应为 `critical`**） |
| `{"debt":{...,"risk_direction":"higher_is_worse"}}` | `within_appetite`（**应为 `critical`**） |
| `{"debt":{"warning":0.5}}` | `warning`（可接受） |

- **500 路径**：`api.py:373-383` 的 `evaluate_policy` 只对 `get_policy` 的 `KeyError` 做了处理，`evaluate_kri` 在 try 之外 → 异常直穿到全局处理器 → HTTP 500。
- **失败开放（fail-open）根因**：`policy.py:12` `direction = limits.get("risk_direction", "high")` 之后仅用 `direction == "high"` 做二分。**任何**非精确 `"high"` 的字符串（大小写差异、拼写错误、空串、`"higher_is_worse"`）都被当作 `"low"` 反向比较，于是超出 `critical` 的值被判为 `within_appetite`。
- `risk_direction` 在仓库中**没有任何配置文件或测试设置**，唯一注入途径就是该 API，因此这是一条完整可达的链路。

```bash
./.venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'backend');\
from finrisk.enterprise.api import PolicyCreate;from finrisk.enterprise.policy import evaluate_kri;\
from finrisk.enterprise.domain import PolicyVersion;\
th=PolicyCreate(name='p',version=1,thresholds={'debt':{'warning':'low','critical':'high'}}).thresholds;\
evaluate_kri(PolicyVersion('pol','org',1,'p',th,'u'),{'debt':0.95})"   # → TypeError
```

### H3 【P2】`FINRISK_ENV` 在同一模块内以两种方式归一化

| 位置 | 归一化 | 用途 |
|---|---|---|
| `api.py:111`（`runtime_components`） | `.lower()` | 生产环境强制 `DATABASE_URL` 校验 |
| `api.py:234`（`persist_agent_snapshot`） | `.lower()` | 生产环境强制 `entity_id` |
| `api.py:181`（bootstrap 守卫） | `.strip().lower()` | 生产环境禁用组织自助注册 |

**实证**：`FINRISK_ENV="production "`（尾随空格）时，前两处得到 `"production "` ≠ `"production"` → **跳过生产环境 DATABASE_URL 强制校验**，静默退化为 `InMemoryEnterpriseRepository` + `CredentialStore`（API 密钥不持久化）；而第三处仍识别为生产 → bootstrap 被禁用。

`api.py:179-180` 的注释正是为修复"大小写"问题而写，但同一修复未应用到另外两处读取。

```bash
./.venv/Scripts/python.exe -c "print(repr('production '.lower()), repr('production '.strip().lower()))"
# 'production ' 'production'   ← 分歧
```

### H4 【P2】`detect_alerts` 违反本仓库自己的"`None` 表示缺失"约定 → `TypeError`

`alerts.py:11,13` 使用 `current.get("severity", 0)` / `current.get("confidence", 1)`。`.get` 的默认值**仅在键不存在时**生效；键存在且值为 `None` 时返回 `None`。

`metrics.py:50-52` 专门以注释说明本仓库用 `None` 表示"缺失"，`alerts.py` 恰是该反模式的实例。实证 4 种输入全部抛异常：

| 输入 | 结果 |
|---|---|
| `{"severity":None,"confidence":None}` | `TypeError: '>' not supported between 'NoneType' and 'int'` |
| `{"severity":None}` | 同上 |
| `{"confidence":None}` | `TypeError: '<' not supported between 'NoneType' and 'float'` |
| `{"severity":"critical"}`（`RiskCase.severity` 的分档字符串） | `TypeError: '>' not supported between 'str' and 'int'` |

当前 `detect_alerts` 仅被 `tests/test_enterprise.py` 引用，属潜伏缺陷。同类 `.get(k, default)` 反模式另见 `api.py:281`（`str(None)` → 存入 `"None"` 作为严重度）与 `api.py:283-284`（`float(None)` → `TypeError`）。

### H5 【P2】`observability.py`：失败阶段被记为"完成"；日志脱敏可绕过

1. **`traced_stage`（`observability.py:61-77`）**：`except` 分支发出 `stage.failed` 后重新抛出，`finally` **无条件**再发出 `stage.completed`。实证失败阶段**同时**产生两条日志：

```json
{"event": "stage.failed", "correlation_id": "", "stage": "assess", "error_type": "RuntimeError"}
{"event": "stage.completed", "correlation_id": "", "stage": "assess", "latency_ms": 0.04}
```

以 `stage.completed` 统计成功率/延迟的看板会把失败计为成功。

2. **`structured_event`（`observability.py:48-51`）**：脱敏集合 `{"api_key","authorization","document_text","prompt"}` 是对 `.lower()` 后键名的**精确匹配**。实证：

| 传入键 | 结果 |
|---|---|
| `api_key` / `API_KEY` / `authorization` / `Authorization` / `document_text` / `prompt` | 已脱敏 |
| `apiKey`（驼峰，`.lower()` = `"apikey"` ≠ `"api_key"`） | **原样落盘** |
| `secret` / `token` / `password` / `header` | **不在集合内，原样落盘** |

### H6 【P2】`workflow.py` 状态机自相矛盾：`reopen_case` 允许 `ACCEPTED → OPEN`

`TRANSITIONS[RiskCaseStatus.ACCEPTED] = {UNDER_REVIEW, CLOSED}`（`workflow.py:14`），但 `reopen_case`（`workflow.py:76-87`）显式接受 `status ∈ {RESOLVED, ACCEPTED}` 并**直接**将 `case.status` 置为 `OPEN`，绕过 `transition_case` 的校验。同一个状态机因此存在两套合法性定义。

### H7 【P2】企业层并发：`transition` 存在丢失更新（状态机约束可被绕过）

`service.transition`（`service.py:110-147`）的流程是 `get_case` → 校验状态机 → 变更 → `save`。PostgreSQL 路径下：

- `postgres.py:98-99` 的 `get_case` 是普通 `SELECT`，**无 `FOR UPDATE`**；
- `postgres.py:57` 的 `save` 是 `ON CONFLICT (id) DO UPDATE`，**无版本号或状态前置条件**。

两个并发请求可同时读到同一 `status`、各自通过 `TRANSITIONS` 校验、后写覆盖先写 → 状态机约束被绕过；且 `ON CONFLICT` 会把并发删除的案件**重新插入**。建议 `get_case` 加 `FOR UPDATE`，或 `save` 加 `WHERE risk_cases.status = %s` 实现乐观锁。

### H8 【P2】`repository.py` 与 `postgres.py` 对未知类型行为不一致

`repository.py:51-64` 的类型分派是一条 `else` 链，末项为 `else self.models`；未知类型（如 `ValidationRecord`）会被**静默写入 `models` 字典**。而 `postgres.py:65-66` 会 `raise TypeError(f"unsupported repository item: ...")`。二者实现同一 `EnterpriseRepository` Protocol，调用方无法依赖任一种行为。

### H9 【P2】原因码词表越界：`contradictions.py` 产出枚举外的值

`DecisionReasonCode` 有 8 个取值。`evaluate_claim_consistency` 实际产出 6 种，其中 **3 种不在枚举内**：

| 产出码 | 在 `DecisionReasonCode` 内 |
|---|---|
| `INSUFFICIENT_EVIDENCE` | 是 |
| `CLAIM_CONTEXT_INCOMPLETE` | 是 |
| `SEVERE_VERIFIED_SIGNAL` | 是 |
| `PARTIAL_NUMERIC_TENSION` | **否** |
| `CLAIM_NOT_OPTIMISTIC` | **否** |
| `NO_ADVERSE_CONFLICT` | **否** |

该码经 `pipeline.py:270` 传入 `classify_tension` → `DisclosureTension.reason_code`，并随 `claim_consistency_evaluations` 一并下发到前端。

**前端侧影响（已核实为"优雅降级"，非崩溃）**：`WhyDecision.tsx:106` 写作 `REASON_COPY[code] ?? "Machine-readable reason recorded on the decision."`，未命中时渲染通用文案。且 `WhyDecision.tsx:72-73` 只从 `decision_reason_codes` / `fusion.reason_codes` 取码，**不读** `claim_consistency_evaluations`，因此这 3 个码当前不会被展示。

**真正的契约缺口**：`types.ts:82,96,153,175,198` 一律把 `reason_code` 声明为 `string`，**没有**与 `DecisionReasonCode` 对应的联合类型，所以 `tsc` 无法发现该越界。同时 `claim_consistency_evaluations` 与 `disclosure_tensions` 两个字段在后端被计算并下发、在 `types.ts:282-283` 被声明、在 `demoFixture.ts` 中存在，但**没有任何组件渲染它们** —— 属"已传输但未消费"的死载荷。

### H10 【P3】企业层其它缺陷

| 位置 | 问题 |
|---|---|
| `applicability.py:45` | `model.lower().replace("_score","").replace("-","_")` 的归一化对**所有真实模型名形式都失败**：`"Altman Z-Score"`→`"altman z_score"`、`"altman_z_score"`→`"altman_z"`、`"Ohlson O-Score"`→`"ohlson o_score"`，均不在 `MODEL_REQUIREMENTS` → `KeyError`。仅裸键 `"altman"` 可用。仓库内因 `enforce_applicability` 用了显式映射表而掩盖；`replace("_score","")` 这一意图（剥离 `_score` 后缀）从未达成。 |
| `governance.py:109-134` | `compare_system_versions` 强制要求 9 个指标，但 `abstention_rate` / `latency_ms` / `cost_usd` 三个**从未参与任何 gate 判断**（required-but-unused）。 |
| `decision.py:30` vs `decision.py:68` | 同一函数内两处证明状态判定不一致：`:30` 用 `.casefold() == "verified"`（大小写不敏感），`:68` 用 `== "verified"`（敏感）。当前后端只产出小写，属潜伏不一致。 |
| `jobs.py:44-50` | `fail`/`complete` 用 `self.jobs[job_id]` 无守卫 → 未知 id 抛 `KeyError`；`Job` 无 `updated_at` 字段，而 `migrations/001` 的 `jobs.updated_at` 为 `NOT NULL`。 |
| `scenario.py:27-32` | 收入冲击**不传导**到 `gross_profit`/`operating_income`，且 `margin_pp` 用的是**原始** `values["revenue"]` 而非已冲击后的收入 → 只做收入冲击时，收入下降而毛利率反向"改善"，下游以毛利率为条件的规则会朝错误方向移动。 |
| `alerts.py:8,14` | 严重度词表混用：`critical`/`high` 与 `warning` 并存，与 `severity.py` 的 5 档（`critical/high/moderate/low/very_low`）不一致。 |
| `storage.py:31-38` | `_safe` 拒绝 `..`/`/`/`\`，但 `pathlib` 会**静默改写**驱动器相对路径（Windows 下 `root/"C:evil"` → `root/evil`），使 `StoredDocument.object_id` 与实际文件名不一致；`"a\x00b"` 在 POSIX 上会被截断为 `"a"`，两个不同 id 映射同一文件。 |
| `tension.py:37-48` | `evidence_sufficiency != "complete"` 时固定给 `confidence = 0.0`；`DisclosureTension.evidence_sufficiency` 的默认值 `"unknown"` 不在 `pipeline.py:270` 的实际取值集合（仅 `"complete"` / `"incomplete_context"`）内。 |
| `evidence_graph.py:51-69` | `paths_to` 遍历**所有**关系类型，包括 `CONTRADICTS` / `WEAKENS` / `INVALIDATES` —— "反向证据"也被计入一条证据路径。 |
| `api.py:373-383` | `evaluate_policy` 的 `metrics: dict[str, float | None]` 是裸 body 参数，**未使用**其它数值端点统一的 `_finite_mapping` 守卫（`api.py:40-50`）。 |
| `api.py:469-479` | `fuse` 用字符串 `req.method == "weighted_average"` 特判参数个数；若 `FUSION_METHODS` 新增元数不同的方法会静默 `TypeError`。（已核当前 4 个方法元数与该特判一致。） |
| `state.py:80-89` | `AgentState.transition` 只禁止"离开终态"，**不校验目标合法性** → 任意非终态可直接跳到任意状态（如 `UNDERSTANDING → COMPLETED`）。 |
| `contradictions.py:16-24` | `_configured` 对未识别的 `operator` 静默退化为 `bool(value)`。当前配置只有 `<`/`>`/`truthy`，但任何算子拼写错误都会变成完全不同的语义。 |
| `migrations/001-003` | 共 17 张表，其中 `jobs` / `documents` / `alerts` / `validation_records` / `decision_bundles` / `temporal_evidence_nodes` / `temporal_evidence_edges` **7 张无任何运行时代码读写**（仅 `api_credentials` 被 `security.py` 使用）→ 这些能力实际只有内存实现，`DecisionBundle` 等审计产物并不落库。 |

### H11 已验证无问题（企业层，避免误伤）

- **`postgres.py` ↔ `migrations/*.sql` 列契约**：逐列核对**位置式** `INSERT INTO ... VALUES`（`organizations` 3 列、`policy_versions` 8 列、`analysis_snapshots` 10 列）与**列名式** INSERT（`risk_cases` 24 列、`entities` 5 列、`model_registry` 16 列、`risk_snapshots` 13 列、`audit_events` 8 列、`api_credentials` 7 列），全部与迁移一致。`resolution_evidence` / `monitoring_state`（002）、`calibration_status` / `api_credentials`（003）均已定义。迁移按 `sorted()` 顺序应用（`api.py:119-120`），001→002→003 的依赖成立。
- **`postgres.py` ↔ `domain.py` / `temporal.py` 位置参数**：`RiskSnapshot` 11 字段 ↔ `list_risk_snapshots` 的 11 个实参；`AuditEvent` 8 字段 ↔ `list_events` 的 `AuditEvent(*row[:-1], str(row[-1]))`；`_case` / `get_policy` / `get_snapshot` / `get_entity` 全部用关键字参数或已核对的顺序。`temporal_evidence_edges.relation` 的 7 值 CHECK 约束与 `EvidenceRelation` 枚举**完全一致**。
- **`decision_bundle.py`**：`build_decision_bundle` → `verify_decision_bundle` 哈希往返**实证返回 `True`**（tuple 与 list 经 `json.dumps` 等价；`to_dict()` 后 `pop` 掉的 3 个键与构建期 `content` 的键集恰好互补）。
- **`security.py`**：`issue_api_key` 用 `secrets.token_hex(16)` + `secrets.token_urlsafe(32)`；`authenticate` 的 `raw.split("_", 2)[:2]` **正确**保留了 `token_urlsafe` 中可能出现的下划线；`verify_api_key` 用 `hmac.compare_digest` 且校验 `active`；`rotate` 保留旧记录并置 `active=False`（而非删除），使旧密钥继续可查但验签失败。
- **`auth.py` / `workflow.py`**：`StrEnum` 与裸字符串的 `hash` / `==` 一致（实证 `PERMISSIONS["admin"]`、`TRANSITIONS["open"]` 均可命中），因此从 DB 读回的字符串做字典查找仍然安全。
- **`contradictions.py` ↔ `config/consistency_policy.json`**：`CHECKS` 引用的 22 个阈值键**全部存在**（无 `KeyError`）；`cash_flow` 类的 `operating_cash_flow_growth` 检查刻意从 `cash_flow_operating_cash_flow_growth` 取阈值，以与 `liquidity` 类的同名检查区分。
- **`scenario.py:59-67`**：`calculate_metrics` 的键集由固定 `specs` 字典决定、与取值无关（`previous=None` 时不含 `*_growth`），故 `stressed_metrics[key]` **不会** `KeyError`。
- **词表一致性**：`llm.ALLOWED_CATEGORIES` 与 `scoring.CATEGORIES` **完全相同**（8 项）；`contradictions.CHECKS` / `EVIDENCE_CONSTRUCTS` 是其子集（缺 `accounting` / `governance_audit`，故这两类叙事声明**无法产生任何数值一致性检查** —— 已计入 C3 同类覆盖缺口）。
- **`enterprise/api.py` 鉴权**：全部业务端点均经 `principal` 依赖鉴权；bootstrap 端点在 `FINRISK_ENV=production` 下被禁用（`bootstrap_enabled`）且要求 token，且 `require_bootstrap_token=True` 而 `bootstrap_token` 未设置时 `expected=""` → `not expected` → 403（**fail-closed**，正确）；bootstrap 端点另配独立限流器（`api.py:200-209`）。`CaseCreate.snapshot_id` 为必填，与 `transition` 的快照要求一致。`risk_timeline` 的 `timeline[index-1]` 有 `if index` 守卫。
- **`fusion.py` 的方法分发**：`FUSION_METHODS` 的 4 个方法中仅 `weighted_average` 需要 `weights`，与 `api.py:474-478` 的特判**一致**（已用 `inspect.signature` 核实）。

---

## I. 研究层（XBRL 解析 / LLM 抽取 / 归一化 / 统计基准）深度审计

### I1 【P0】`parse_companyfacts` 会把"上一年度比较数"当作本年度数

**位置**：`backend/finrisk/xbrl.py:192-200`（`_annual_candidates`）、`:226-232`（候选选择）、`:255`（`restated` 判定）

**原因**：SEC `companyfacts` 中，一份 FY2023 10-K 会同时包含 FY2023 与 FY2022 两个年度的数据，而这两组数据的 `fy` / `fp` / `form` / `filed` / `accn` **完全相同**。`_annual_candidates` 只按这 5 个字段过滤，**不做 `start` / `end` 期间匹配**，随后：

```python
candidates.sort(key=lambda x: (x.get("filed", ""), x.get("accn", "")))
candidate = candidates[-1]
```

取到的是**按 JSON 数组顺序**的最后一个元素。

**实证**（真实 AAPL FY2023 10-K，未做任何改写）：

```
原顺序    → revenue fy=2023 value=394,328,000,000  period=2022-01-01..2022-12-31  restated=True
数组倒序  → revenue fy=2023 value=383,285,000,000  period=2023-01-01..2023-12-31  restated=True

FY2023 真实 revenue = 383,285,000,000 ; FY2022 = 394,328,000,000
total_assets 同样受影响：返回 352,755,000,000（FY2022 值），真实 352,583,000,000
```

即：**同一份文件，仅把 JSON 条目顺序颠倒，解析结果就在 FY2023 与 FY2022 之间翻转**；同时 `restated=True` 被误置 —— 它把"比较期数据"误判成了"重述"。

**为何未被发现**：`tests/test_xbrl.py` 的夹具只覆盖"重述（restatement）"场景，**从未构造过含比较期的 10-K** —— 这正是该盲点。

**同仓库内已有正确实现**：`sec_bulk.py` 的 `build_companyfacts_corpus` 同时锚定 `accn` + `end`，`build_numeric_corpus` 锚定 `adsh` + `period` —— 修复方案在仓库内已存在，可直接照搬。

### I2 【P1】`llm.py` 异常元组遗漏 `IndexError` / `AttributeError`，绕过重试与成本日志

**位置**：`backend/finrisk/llm.py:195`、`:208`

```python
for attempt in range(1, self.max_retries + 2):
    ...
except (KeyError, TypeError, ValueError, ValidationError,
        urllib.error.URLError, OSError) as exc:
```

**实证**：

| 上游响应 | 结果 | 重试次数 | 调用日志 |
|---|---|---|---|
| `{"choices": []}` | `IndexError` 直接抛出 | **0** | **无** |
| `{"usage": null}` | `AttributeError` 直接抛出 | **0** | **无** |
| 缺少 `choices` 键 | `KeyError` | 3 | 有 |
| 非法 JSON | `ValidationError` | 3 | 有 |

即：一个语法合法但结构退化的上游响应会**完全绕过重试与成本/调用日志**。`orchestrator.py:98-100` 会捕获它并降级为 `semantic_failed`，因此不会 500，但该次 LLM 调用在成本审计中**不可见**。

**另**：`provider_from_env()`（`llm.py:219-233`）**从不传 `api_key`**，`StructuredLLMProvider` 只能回落到 `os.getenv("OPENAI_API_KEY")`；`FINRISK_LLM_API_KEY` 不被支持。

**另**：`SCHEMA`（`:120-141`）与 `ClaimOutput` / `NarrativeOutput` 的 Pydantic 约束不对齐 —— `claim` / `evidence_text` 声明 `{"type":"string"}` 无长度约束但模型强制 `min_length=3, max_length=500` / `1200`；`qualifiers` 无 `maxItems` 但 `max_length=20`；`required_evidence_types` 有 `minItems:1` 但 `max_length=10`；`NarrativeOutput.claims` 有 `max_length=100` 但 SCHEMA 无 `maxItems`。即：**结构合法但超长的响应会在 Pydantic 校验层失败**（被 `ValidationError` 捕获并重试，属可容忍，但三次重试都会失败）。

### I3 【P1】`parse_number` 对"千分位 + 小数"的数值一律返回 `None`

**位置**：`backend/finrisk/normalization.py:58-65`

```python
if re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw):
    raw = raw.replace(",", "")
else:
    raw = raw.replace(",", ".")
```

**实证**：

| 输入 | 期望 | 实际 |
|---|---|---|
| `'1,234'` | 1234.0 | 1234.0 ✓ |
| `'1,234,567'` | 1234567.0 | 1234567.0 ✓ |
| `'1234,56'`（欧式小数） | 1234.56 | 1234.56 ✓ |
| `'1,234.56'` | 1234.56 | **`None`** |
| `'12,345.6'` | 12345.6 | **`None`** |
| `'(1,234.56)'` | -1234.56 | **`None`** |
| `'1,234.56%'` | 0.0123456 | **`None`** |

**原因**：`fullmatch` 不容许小数点，于是落入 `else` 分支把逗号替换成点 → `float("1.234.56")` → `ValueError` → `return None`。对美股/美式财报，`"1,234.56"` 是**最常见写法**，结果是静默丢弃（在 PDF 抽取路径中表现为"字段缺失"，只降低 `evidence_coverage` 而不报错）。

**覆盖率证据**：`normalization.py` 的未覆盖行恰为 `64-65`，即 `except ValueError: return None` —— 该分支从未被测试执行。

### I4 【P1】`parser.py` 的 `_SCALE_PATTERN` 把正文里的 `000` 当成"千"量纲 → 1000× 错误

**位置**：`backend/finrisk/parser.py:21-23`、`:57`

```python
_SCALE_PATTERN = re.compile(r"(thousands?|millions?|billions?|000s|000|mn|mm|bn)\b", re.IGNORECASE)
```

**实证**：`_SCALE_PATTERN.search("Revenues increased to $1,000,000 in 2023")` 命中 `'000'` → 量纲判为 `thousands` → 1,000,000 被放大为 **1e9**。

该正则的本意（见 `parser.py:10-15` 注释）是识别**表头**里的量纲声明，但 `000` 这一分支也会命中任何以 `000` 结尾的正文数字，产生 1000× 错误 —— **正是注释声称要避免的那类错误**。`header = " ".join(text.splitlines()[:15])`（`:57`）意味着只要前 15 行出现这类数字就会触发。

### I5 【P1】`selective_metrics` 把"未知"排成"最不危险"

**位置**：`backend/finrisk/benchmark_protocol.py:173-203`

排序键写作 `probabilities[index] if probabilities[index] is not None else -1`，即 `None`（未知/弃权）被赋予 `-1`，排在**所有真实概率之前**。

**实证**：`labels=[1,0,1,0]`、`probs=[0.9,0.1,None,0.05]` → `risk_ranking=[0,1,3,2]`，未知项排最后。

在"选择性预测"评估里，这等于声称"模型弃权的样本是最安全的" —— **方向性错误**，会系统性抬高选择性指标。

### I6 【P1】`research_eval.py`：两个硬编码指标 + 三个算术代理消融

**位置**：`backend/finrisk/research_eval.py:213-214`、`:226-234`

- `:213` `"unsupported_claim_rate": 0.0` 与 `:214` `"evidence_precision": 1.0 if sum(...) else None` 是**硬编码常量**，与当次运行无关。
- 三个消融项是**算术代理**，并未真正重跑：

```python
"without_narrative": _probability("rule_engine", base),
"without_rules": (_probability("ratios_only", base) + _probability("traditional_models", base)) / 2,
"without_models": (_probability("ratios_only", base) + _probability("rule_engine", base)) / 2,
```

**实证（误差 < 1e-9）**：`without_narrative` 与 `rule_engine` 的三项指标（0.7625 / 0.35 / 1.0）**完全相同**；`without_rules`、`without_models` 等于对应两项的算术平均。

- 唯一真正的消融是 `without_trends`（`:236-244`，以 `previous=None` 真实重跑 pipeline）。

这不影响门禁（测试只断言 baseline 名称集合），但会直接影响任何引用"消融实验"结论的文档。

### I7 【P2】`benchmark.py` 把 `confidence` 标成 `coverage`

**位置**：`backend/finrisk/benchmark.py:29`

```python
else: output={"overall_score": ..., "risk_level": ..., "coverage": assessment.confidence}
```

**实证**：同一次评估 `assessment.confidence = 0.45`，而 `assessment.evidence_coverage = 0.0`。写入 JSONL 的 `coverage` 字段是"证据质量置信度"而非"证据覆盖率" —— 二者在本仓库中是**语义不同的两个量**（`pipeline.py:318` 同时传出 `evidence_quality=conf` 与 `evidence_coverage=evidence_coverage`）。

该行虽被执行（覆盖率显示 `benchmark.py` 仅第 34 行未覆盖），但 `tests/test_benchmark.py` 只断言 `baseline` 名称集合，**从不校验字段值**。

### I8 【P2】两个同名 `BASELINES` 常量，词表不同

| 文件 | 取值 |
|---|---|
| `benchmark.py:9` | `llm_only, ratios_only, rules_only, models_only, full_hybrid, hybrid_without_narrative, hybrid_without_trends` |
| `research_eval.py:23` | `llm_only, ratios_only, rule_engine, traditional_models, full_hybrid` |

交集仅 3/7。`rules_only` vs `rule_engine`、`models_only` vs `traditional_models` 指同一概念却不同名；任何跨模块按名字对齐 baseline 的代码都会静默漏项。（已核实二者各自内部自洽，不是导入错误。）

### I9 【P2】FCF 符号约定在两处不一致

| 位置 | 表达式 |
|---|---|
| `metrics.py:49` | `ocf - abs(capex)` |
| `metrics.py:124` | `previous_ocf - abs(previous_capex)` |
| `sec_bulk.py:422` | `ocf - capex`（**未取绝对值**） |
| `sec_bulk.py:472` | `ocf - capex`（**未取绝对值**） |

SEC 的 `PaymentsToAcquirePropertyPlantAndEquipment` 等 tag 的 `value` 为**负数**，因此 `sec_bulk` 的 `ocf - capex` 实际等于 `ocf + |capex|` → **FCF 被高估 2×|capex|**，且 `FCF_NEGATIVE_TWO_SUBSEQUENT_PERIODS` 恶化条件被系统性推向 **False**。`metrics.py` 的 `abs()` 才是正确约定。

### I10 【P2】`extraction_reference.py` 只捕获 `ValueError`，但 `csv` 会给出 `None`

**位置**：`backend/finrisk/extraction_reference.py:75-79`、`:110`

```python
def _line(row: dict[str, str]) -> int:
    try:
        return int(row.get("line", ""))
    except ValueError:
        return 2**31 - 1
```

`csv.DictReader` 对**缺失的尾部字段**返回 `None`（而非 `""`），于是 `int(None)` → **`TypeError`（未被捕获）**。同理 `:110` 的排序键 `row.get("report", "")` 在短行时返回 `None` → `TypeError: '<' not supported between instances of 'str' and 'NoneType'`。

### I11 【P2】`numeric_benchmark.temporal_trajectories` 在 `risk` 为 `None` 时崩溃

**位置**：`backend/finrisk/numeric_benchmark.py:108`

```python
"delta": points[-1]["risk"] - points[0]["risk"]
```

**实证**：首/末点 `risk` 为 `None` → `TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'`。覆盖率证据：未覆盖行为 `45, 75, 80, 106`，其中 `106` 是 `<2` 行的 `continue`（从未测试单点 ticker），而 `108` 的减法虽被执行却从未遇到 `None`。

### I12 【P2】`xbrl.CONCEPTS` 与 `sec_bulk.CONCEPT_ALIASES` 别名表分歧

| 字段 | `xbrl.py` | `sec_bulk.py` |
|---|---|---|
| `capital_expenditure` | 1 个别名 | 3 个别名 |
| `short_term_debt` | `ShortTermBorrowings, ShortTermDebtCurrent, LongTermDebtCurrent` | `ShortTermBorrowings, LongTermDebtCurrent, DebtCurrent` —— **`DebtCurrent` 位于优先级 1，遮蔽 `LongTermDebtCurrent`** |
| 瞬时字段集合 | 13 项 | 11 项（缺 `accounts_payable`、`retained_earnings`） |

同一概念在"在线 XBRL 归一化端点"与"批量语料构建"两条路径上会取到不同的 XBRL tag，从而产生不同的数值。

### I13 【P2】`benchmark_protocol` 内两个同名族的失败语义不一致

- `fit_decision_stump`（`:156-170`）**缺少** `fit_logistic_baseline` 具备的矩形校验。实证：`[[]]` → `TypeError`；锯齿数组 → `IndexError`。
- `calibration_curve`（`:206-226`）会把越界概率**静默丢弃**，且 `bins=0` 静默返回 `[]`；而 `evaluation.expected_calibration_error` 对 `bins<1` 会 `raise ValueError`。
- `evaluation.roc_auc` / `confusion_matrix` 缺少长度一致性校验（`expected_calibration_error` 有）。

### I14 已验证无问题（研究层，避免误伤）

- `research_eval.py:208-210` 调用 `expected_calibration_error(probabilities, [bool(x) for x in true], bins=3)` 的**实参顺序正确**。该模块签名是 `(confidences, correct)`，而 `enterprise/calibration.py` 是 `(labels, probabilities)` —— 属真实存在的**同名异序陷阱**，但本处用法无误（审计中曾因此产生过一次误报，已修正）。
- `empirical_validation.py` 全文 615 行内部自洽：`PointInTimeGuard`、`_fact_provenance_valid`（含环检测与 `DERIVED_VALUE_MISMATCH`）、`validate_dataset_integrity` 的泄漏/切分/哈希门禁、`company_clustered_bootstrap_delta` 的聚类自助法均无缺陷。
- `sec_bulk.py` 的 `build_companyfacts_corpus`（锚定 `accn` + `end`）与 `build_numeric_corpus`（锚定 `adsh` + `period`）比较期处理**正确** —— 与 I1 的 `xbrl.py` 形成对照。
- `extraction_reference.construct_pre_num_reference` 的 `qtrs` 判定（瞬时字段 `{"0",""}`，流量字段 `{"4","","0"}`）与 FSDS 语义一致。
- `tools/registry.py` 的 `_verify`（`:158-167`）确实调用 `verify_conclusions` 真实门禁（注释所述"曾经是恒等函数"已修复）；`_models`（`:170-183`）与 `pipeline.py:177-181` 的模型装配逻辑**逐项等价**（`working_capital` 取 `metrics[...].value`、`ebit` 回落 `operating_income`、仅 `previous` 存在时才加 Beneish/Piotroski、最后 `enforce_applicability`），不存在双实现分歧。
- `agent/planner.py`、`agent/reflection.py`、`agent/tool_registry.py`、`research_schema.py` 无缺陷。

---

## J. 脚本、测试与迁移契约（覆盖盲区）

### J1 【P1】6 个脚本没有 `__main__` 守卫，`import` 即产生副作用

| 脚本 | 导入时的副作用 |
|---|---|
| `scripts/generate_public_sample.py` | **覆写两个已跟踪文件** `examples/intel_2024_sample_report.txt` / `.pdf` |
| `scripts/run_benchmark.py` | `parse_args()` + 写 `research/results/synthetic_smoke.jsonl` |
| `scripts/verify_docker_health.py` | **阻塞轮询 90 秒**后 `raise SystemExit` |
| `scripts/validate_postgres_migration.py` | `os.environ["DATABASE_URL"]` → 未设置则 `KeyError` |
| `scripts/validate_decision_benchmark.py` | `parse_args()` 缺必填位置参数 → `SystemExit(2)` |
| `scripts/run_demo.py` | 跑完整评估并打印报告 |

（其余 16 个脚本均有 `if __name__ == "__main__":`。）

**后果**：任何 `pytest --doctest-modules`、`importlib` 扫描、IDE 索引或打包工具触达 `scripts/` 都会执行真实计算并改写产物；`verify_docker_health.py` 更会挂起 90 秒。

### J2 【P1】已提交的示例报告与当前代码输出**不一致**（陈旧产物）

上一条的直接证据。仅执行 `import scripts.generate_public_sample`，`examples/intel_2024_sample_report.txt` 即被改写，与已提交版本出现实质性差异：

| 字段 | 已提交版本 | 当前代码重新生成 |
|---|---|---|
| Overall Risk | **42.7/100 (Moderate)** | **39.1/100 (Low)** |
| cash_flow 维度 | 44/100 (Moderate)，驱动 `CFL_002, CFL_004, CFL_007` | 34/100 (Low)，驱动 `CFL_002, CFL_004`（**CFL_007 不再触发**） |
| 头部文案 | `Confidence: 0.65` / `Confidence is an uncalibrated evidence-coverage score:` | `Evidence quality index: 0.65 (UNCALIBRATED; not a probability)` / `Evidence-quality components:` |
| 缺失项 | 无 `cfo_to_net_income` | 新增 `cfo_to_net_income: N/A — Denominator is zero` |
| Ohlson 缺失分量顺序 | `funds_from_operations, prior_net_income, gnp_price_index` | `funds_from_operations, gnp_price_index, prior_net_income` |

即：**已提交示例所展示的风险等级（Moderate）与当前代码实际产出的等级（Low）不同**。`research/error_analysis.md:7,17` 与 `research/results.md:53` 引用的 42.7 属冻结试点口径，但 `examples/` 下这份**可再生成**的产物已明显漂移。

审计期间已用 `git checkout --` 复原这两个文件，未在仓库留下任何改动。

**另**：该脚本 `:10` 把 `example["filing_url"]` 作为第 6 个位置实参传入，而对应形参是 `document`（文档标题），因此报告中的"文档名"实际是一个 URL。

### J3 【P2】`export_pdf` 是覆盖率最低的函数，却产出已提交产物

覆盖率实测（`pytest --cov=finrisk`，总计 92%）：

| 模块 | 覆盖率 | 未覆盖行 | 说明 |
|---|---|---|---|
| `report.py` | **53%** | `26-42` | **整个 `export_pdf` 函数体未覆盖**，而 `examples/intel_2024_sample_report.pdf` 正是它的产物 |
| `alerts.py` | 80% | `10,12,14` | 三个告警 append 分支（对应 H4 的 `TypeError` 路径） |
| `tools/ingestion.py` | 84% | `14,17,28,83,103-104` | XBRL 摄取路径基本未覆盖 |
| `workflow.py` | 86% | `23,33,51,70,78,80` | `78/80` 正是 `reopen_case` 的两个 `raise`（对应 H6） |
| `human_study.py` | 86% | `16,18,25` | **`validate_study_rows` 的非法行分支与 `raise` 全部未覆盖** |
| `severity.py` | 88% | `29,39` | 负分回落分支（`score < 0` 时返回 `very_low`） |
| `governance.py` | 89% | `127,129,131` | `compare_system_versions` 的门禁行（对应 H10） |
| `calibration.py` | 90% | `14,31,48,52,61` | 含 `minimum_reliability` 相邻分支（对应 H10） |
| `normalization.py` | 92% | `64-65` | **正是 I3 的 `except ValueError: return None`** |
| `observability.py` | 92% | `66-70` | `traced_stage` 的 `except` 块（对应 H5 的"失败也报完成"） |
| `metrics.py` | 94% | `34-35,112,128` | `_safe_div` 的 `OverflowError` 分支；EBITDA 非正时的 `debt_to_ebitda` 注记 |
| `scenario.py` | 94% | `26,49,51` | 债务父项解析、应收/存货冲击（`30` 的 `margin_pp` 用冲击前收入已执行但无断言，对应 H10） |
| `contradictions.py` | 95% | `167,174-177` | **正是 H9 的 `PARTIAL_NUMERIC_TENSION` / `NO_ADVERSE_CONFLICT` 两行** |
| `numeric_benchmark.py` | 95% | `45,75,80,106` | 对应 I11 |
| `temporal.py` | 96% | `52,80,84` | `52` 跨实体守卫；`80/84` = `deteriorating` / `recovery` 两个轨迹标签从未被测出 |
| `benchmark.py` | 96% | `34` | `write_jsonl` 函数体 |
| `evaluation.py` | 98% | `18` | `unsupported_claim_rate` 函数体（对应 I6 的硬编码 `0.0`） |
| `models.py` | 99% | `18` | `_logistic` 的 `x >= 700` **上**钳位（下钳位已覆盖） |

**规律：本报告确认的几乎每一个缺陷，都恰好落在未覆盖行上。** 这不是巧合 —— 覆盖率缺口就是缺陷的藏身处。

### J4 【P2】前端只有 4 个测试，全部集中在一个 24 行的纯函数模块

`frontend/test/presentation.test.mjs` 共 **4 个断言**，仅覆盖 `lib/presentation.mjs`（`displayScore` / `displayReliability` / `normalizeDecision` / `evidenceLocator` / `safeApiJson`）。

**零测试**：

- `lib/api.ts` —— 形状守卫、超时、错误映射（B2 的所在）
- 全部 8 个组件 —— `EvidenceTrail` / `WhyDecision` / `DimensionGrid` / `DecisionPaths` / `TelemetryPanel` / `DecisionSummary` / `PilotTable` / `IntakePanel`（B3 的 20+ 处无防护访问）
- `app/api/v1/[...path]/route.ts` —— A1 的 P0 缺陷所在
- 错误边界 —— B1：文件尚不存在

这直接对应用户"前端要确保有很强的稳健性"的要求：**当前前端没有任何自动化机制能发现渲染崩溃。**

### J5 【P2】迁移表与运行时契约：16 张表中 7 张无任何 SQL 读写

逐条核对 `migrations/*.sql` 与 `backend/finrisk/**/*.py` 的 SQL 字面量（已确认不存在动态表名）：

| 表 | 状态 |
|---|---|
| `organizations` / `entities` / `policy_versions` / `risk_cases` / `audit_events` / `analysis_snapshots` / `risk_snapshots` / `api_credentials` | 完整读写 ✓ |
| `model_registry` | **只写不读**（仅 `postgres.py:63` 的 INSERT/UPDATE，无任何 SELECT） |
| `documents` | **无任何 SQL** —— 文档实际存 `LocalDocumentStorage` 文件系统 |
| `jobs` | **无任何 SQL** —— `JobQueue` 仅内存实现 |
| `alerts` | **无任何 SQL** —— `detect_alerts` 仅返回内存列表 |
| `validation_records` | **无任何 SQL**，且 `ValidationRecord` **无任何可用的持久化路径**：`PostgresEnterpriseRepository.save()` 的类型分派只认 6 种（`Organization` / `Entity` / `PolicyVersion` / `RiskCase` / `AnalysisSnapshot` / `ModelRecord`），其余抛 `TypeError`；`InMemoryEnterpriseRepository.save()` 则**静默落到 `self.models`**（H8） |
| `decision_bundles` | **无任何 SQL** —— `DecisionBundle` 只在内存构建并随响应返回，不落库 |
| `temporal_evidence_nodes` / `temporal_evidence_edges` | **无任何 SQL** —— `EvidenceGraph` 仅内存实现（该表 `relation` 的 7 值 CHECK 与 `EvidenceRelation` 一致，但无人写入） |

即：**`DecisionBundle`、证据图、作业队列、告警、文档元数据这五项"企业能力"目前只有内存实现，迁移脚本里的表是空壳。** 对外文档若宣称"审计产物落库"，则与实际不符。

### J6 已验证无问题（脚本 / 测试 / 迁移，避免误伤）

- **导入契约**：`scripts/*.py` 与 `tests/*.py` 中 **319 处** `finrisk` 导入**全部解析成功**，无改名/删除后的悬空引用。
- **签名契约**：以 `inspect.signature` 比对 **523 处**调用点，位置参数个数、关键字名、必填参数**全部匹配**。唯一告警 `tests/test_decision_grade.py:367` 的 `AnalysisSnapshot(**state.analysis_snapshot)` 是 `**` 解包导致的静态误报。
- **版本号一致**：`api.py:320`、`demoFixture.ts:22`、`page.tsx:125,242`、`verify_docker_health.py:22` 的 `v0.3.2` 互相一致。（仅 `page.tsx:125` 的 `?? "v0.3.2"` 回落值属重复字面量，升版时易漏改。）
- `tests/test_claimed_capabilities_are_wired.py`（151 行）是质量较高的**跨组件装配回归**测试，覆盖 8 条曾经存在过的真实缺陷（轨迹与决策一致、抽取仅执行一次、声明分类不可自相矛盾、对外分数即决策来源分数等），是本仓库最有价值的测试文件。
- `tests/test_xbrl.py`、`tests/test_benchmark.py` 覆盖面窄，但**断言本身不虚假**（不是"自证式"测试）—— 它们只是没覆盖到 I1 / I7 的场景。
- `migrations/*.sql` ↔ `postgres.py` 的**列契约逐列核对无误**（详见 H11）。
- 测试目录无需 `__main__` 守卫（pytest 风格），不构成缺陷。
