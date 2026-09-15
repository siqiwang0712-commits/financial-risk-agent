# 审计整改记录（对应 `docs/audit_report_2026-09-13.md`）

- 整改日期：2026-09-14
- 整改对象：`C:\Document\Finrisk\financial-risk-agent`（基线 HEAD `6688c0f`）
- 范围：仅本仓库内文件；未执行任何 `git push`；未修改仓库外文件
- 门禁结果：`ruff` 无告警；`pytest` **362 passed / 3 skipped**，覆盖率 **93.48%**（阈值 90%，基线 92%）；
  `tsc --noEmit` 通过；`next build` 成功；`node --test` **21 passed**；
  `git diff --check` 干净；`scripts/replay_frozen_experiment.py` 三个实验的冻结产物哈希均一致
  （3 个 skipped 是需 PostgreSQL 的用例，CI 会执行）

> 逐条状态：**已修** = 代码改动；**已披露** = 报告本身给出的可选方案（产品决策类），以文档 + 载荷字段 + 测试固定。

## P0（4 条）

| 编号 | 状态 | 修复 | 验证 |
|---|---|---|---|
| A1 代理转发上游 `content-length` | 已修 | 响应头白名单移除 `content-length`，仅在流式透传的成功分支重新附加；逻辑抽到 `frontend/lib/proxy.mjs` 以便测试 | `frontend/test/proxy.test.mjs`（4 条）断言替换后的 body 不再携带上游长度 |
| B1 无错误边界 | 已修 | 新增 `app/error.tsx`、`app/global-error.tsx`、`components/PanelBoundary.tsx`，`page.tsx` 按标签页包一层局部边界 | `next build` 通过；边界按 `activeTab` 加 key，切换标签即清除失败态 |
| D1 `/assess` 触发未捕获 `StopIteration` → 500 | 已修 | `next(..., None)` 后抛显式 `ValueError`（说明缺前期数据）；`/assess` 已有的 `except ValueError` 将其映射为 422 | `test_audit_fixes.py::test_caller_supplied_model_metric_is_a_value_error_not_a_stop_iteration`、`::test_assess_endpoint_maps_a_caller_supplied_model_metric_to_422` |
| I1 XBRL 把比较期当本期 | 已修 | 候选选择改为按事实自身期间（`end` → `filed` → `accn`）取最大；`restated` 只比较同期间的值；新增 330–400 天的年度期间守卫剔除季度期间 | `::test_xbrl_selects_the_current_year_not_the_comparative`（正序/倒序结果一致）、`::test_xbrl_selects_the_latest_instant_for_instant_items`、`::test_xbrl_still_detects_a_genuine_restatement`、`::test_xbrl_ignores_a_quarterly_duration` |

## P1（14 条）

| 编号 | 状态 | 修复 | 验证 |
|---|---|---|---|
| A2 试点表覆盖率列取错数据源 | 已修 | 按 `example_id` 关联 `predictions.json` 的逐公司 `evidence_coverage`；数据集均值改名 `dataset_evidence_coverage` | `::test_public_pilot_publishes_per_company_coverage_not_the_dataset_mean`（0.65/0.45/0.65） |
| B2 `analyzeDocument` 无形状校验、无超时 | 已修 | 接入 `isAssessmentPayload` 守卫；新增 120s 超时 | 守卫由 `frontend/test/guards.test.mjs` 覆盖；超时防止按钮永久禁用 |
| B3 6 组件 20+ 处无防护访问 | 已修 | `WhyDecision`/`EvidenceTrail`/`DimensionGrid`/`DecisionPaths`/`AgentTrace`/`TelemetryPanel` 全部改为可选链 + 兜底文案 | 局部错误边界保证单个面板失败不白屏 |
| C3 25/68 规则永不触发 | 已披露 | 新增 `rules.RuleCoverage` / `rule_coverage()`，每次评估随载荷发布 `rule_coverage`；README 与 `docs/capability_maturity_matrix.md` 披露 **43/68** 可达；文本报告新增 `RULE COVERAGE` 段 | `::test_rule_coverage_quantifies_the_dead_rule_gap`、`::test_every_assessment_publishes_its_rule_coverage`、`::test_the_text_report_publishes_rule_coverage` |
| D2 `llm_unavailable` 语义错误 | 已修 | 改用 `semantic_failed` | `::test_rejected_claims_are_not_reported_as_an_llm_outage` |
| H1 3 个 `RiskDomain` 取值不可达 | 已修 | 显式声明 `UNPRODUCED_RISK_DOMAINS` / `PRODUCED_RISK_DOMAINS`；`disclosure_tension` 获得真实产出方；门禁抽成 `decision.verified_paths_for_domain`，`service.py` 与 `enterprise/api.py` 共用 | `::test_every_risk_domain_is_either_producible_or_declared_unproducible`、`::test_verified_paths_for_domain_applies_the_dimension_alias`、`test_enterprise_api_endpoints.py::test_a_case_cannot_be_accepted_without_a_matching_evidence_path` |
| H2 策略阈值契约缺口（500 / 失败开放） | 已修 | `policy.normalize_direction` 只接受 `high`/`low`（大小写、空白不敏感），未知值抛错；新增 `validate_thresholds` 在 `PolicyCreate` 校验；`evaluate_kri` 异常映射为 422 | `::test_an_unrecognised_risk_direction_is_rejected_not_read_as_low`、`::test_an_uppercase_risk_direction_still_breaches`、`::test_validate_thresholds_rejects_what_evaluate_kri_cannot_evaluate`、`test_enterprise_api_endpoints.py::test_a_malformed_policy_is_refused_at_the_boundary` |
| I2 LLM 异常元组漏 `IndexError`/`AttributeError` | 已修 | 异常元组补齐；`provider_from_env()` 支持 `FINRISK_LLM_API_KEY` | `::test_a_degraded_upstream_response_is_retried_and_logged`、`::test_provider_from_env_reads_the_project_prefixed_api_key` |
| I3 `parse_number` 丢弃"千分位+小数" | 已修 | 按"最后一个分隔符"判定美式/欧式，`1,234.56` → 1234.56 | `::test_parse_number_handles_both_separator_conventions` |
| I4 `_SCALE_PATTERN` 命中正文 `000` | 已修 | 加词边界 `(?<![\w,])` / `(?![\w,])`，`000` 仅在独立 token 时生效 | `::test_scale_pattern_does_not_read_a_body_number_as_a_scale` |
| I5 `selective_metrics` 把未知排成最安全 | 已修 | 弃权样本单列 `abstained`，不再进入风险排序 | `::test_abstentions_are_reported_separately_and_never_ranked_as_safe` |
| I6 消融为算术代理 + 硬编码指标 | 已修 + 已披露 | 移除硬编码的 `unsupported_claim_rate: 0.0` / `evidence_precision: 1.0`，改为真实测量 `verified_claim_coverage` 及其补数；新增 `ABLATION_METHODS` 把五个消融各自的方法（`baseline` / `arithmetic_proxy` / `rerun`）作为数据随行发布，`research/ablation.md` 逐条说明 | `::test_the_pilot_summary_measures_claims_instead_of_publishing_constants`、`::test_ablation_methods_are_declared_and_only_one_is_a_real_rerun` |
| J1 6 个脚本无 `__main__` 守卫 | 已修 | 6 个脚本改为 `main()` + 守卫；22 个脚本现已全部有守卫 | `test_script_import_guards.py`（8 条，含"导入不得改写 `examples/`"） |
| J2 示例报告陈旧 | 已修 | 修正把 `filing_url` 传给 `document` 形参的错误；重新生成 `.txt`/`.pdf`（42.7/Moderate → 39.1/Low） | `test_script_import_guards.py::test_public_sample_is_regenerable_and_matches_the_committed_artifact`（逐字节比对） |

## P2（33 条，按报告分组）

| 编号 | 状态 | 修复 | 验证 |
|---|---|---|---|
| A3 `role_review.analyst` 类型声明不符 | 已修 | 新增 `AnalystJudgement[]` 联合类型 | `tsc --noEmit` 通过 |
| B4 渲染细节（9 处） | 已修 | `displayScore` 四舍五入、`displayRatio` 兜底、`page` 哨兵显式化、`band(undefined)`、`overall_score == null`、`annotation_status` 兜底、`key` 改用 `filing`、`IntakePanel` 空年份、CSP 开发期 `'unsafe-eval'` | `frontend/test/presentation.test.mjs`（12 条） |
| C4 `evidence_quality` 与 `confidence` 同值 | 已披露 | 载荷新增 `confidence_semantics`，`domain.py` 注明二者是同一指数的两个名字；`DecisionSummary` 增脚注说明 | `::test_confidence_and_evidence_quality_are_documented_as_one_index` |
| D3 其它（4 项） | 已修 | orchestrator 未知模型不再归为 Ohlson（`facts.MODEL_NAMES_BY_KEY`，未知键转 warning）；`evidence_paths` 冲突键加后缀不丢路径；`roc_auc`/`confusion_matrix` 补长度与二值校验；欧式 `1.234,56` 已支持 | `::test_roc_auc_and_confusion_matrix_reject_misaligned_input`、`::test_applicability_model_names_normalize_to_the_requirement_keys` |
| H3 `FINRISK_ENV` 两种归一化 | 已修 | 抽出 `_environment()`，三处共用 `.strip().lower()` | `::test_a_trailing_space_in_finrisk_env_still_enforces_production_storage`、`::test_a_lower_case_environment_value_is_also_normalized`（独立解释器验证） |
| H4 `detect_alerts` 违反 `None` 约定 | 已修 | `_numeric()` 把 `None`/非数值视为缺失；严重度词表统一到 `severity.py` 五档 | `::test_detect_alerts_tolerates_none_and_non_numeric_values`、`::test_detect_alerts_still_reports_a_real_worsening` |
| H5 失败记为完成 + 脱敏可绕过 | 已修 | `traced_stage` 失败分支不再触发 `stage.completed`；`_normalize_field` 重写（修复 **`API_KEY` 漏脱敏** 的回归），并增加后缀规则覆盖 `access_token` 等 | `::test_a_failed_stage_is_not_also_reported_as_completed`、`::test_log_redaction_covers_camel_case_and_common_secret_names`（9 种拼写） |
| H6 `reopen_case` 绕过状态机 | 已修 | `ACCEPTED → OPEN` 写入 `TRANSITIONS`，`reopen_case` 改走 `transition_case`（保留原有可达性，消除"两套合法性定义"） | `::test_reopen_moves_through_the_declared_transition_table`、`::test_every_declared_transition_is_reachable_through_transition_case` |
| H7 `transition` 丢失更新 | 已修 | 新增 `save_case_transition(case, expected_status)` 做 CAS；内存与 PostgreSQL 两实现同语义 | `::test_a_concurrent_status_change_is_rejected_rather_than_overwritten`、`test_enterprise_api_endpoints.py` 生命周期用例 |
| H8 仓储未知类型行为不一致 | 已修 | 内存实现改为 `raise TypeError`，与 PostgreSQL 一致 | `::test_an_unsupported_repository_item_is_rejected_in_both_implementations` |
| H9 原因码词表越界 | 已修 | 新增 `ClaimConsistencyReasonCode` 闭合词表（6 值）；`tension` 默认码改由分类推导，不再复用决策词表；前端为两个词表各建联合类型 | `::test_the_claim_consistency_vocabulary_is_closed_and_distinct`、`::test_every_produced_reason_code_is_in_the_declared_vocabulary`、`::test_a_tension_reason_code_is_derived_from_its_classification` |
| H10 企业层其它（13 项） | 已修 | 模型名归一化（`model_key`）、治理门禁/上报指标分离、证明状态判定统一 `casefold`、`jobs` 未知 id 报错并补 `updated_at`、收入冲击传导到毛利率相关行且 `margin_pp` 用冲击后收入、存储标识改白名单 + 路径包含校验、`evidence_sufficiency` 词表闭合、`paths_to` 只跟随支持关系、`evaluate_policy` 补数值守卫（含布尔）、`fuse` 改按签名分派、`state.transition` 增合法转移表、`_configured` 未知算子抛错 | `test_audit_fixes.py` 的 H10 组 + `test_audit_coverage_gaps.py` + `test_enterprise_api_endpoints.py` |
| I7 `benchmark.py` 把 `confidence` 标成 `coverage` | 已修 | 拆成 `evidence_quality` / `evidence_coverage` 两个字段 | `::test_smoke_benchmark_publishes_quality_and_coverage_under_separate_names` |
| I8 两个同名 `BASELINES` | 已修 | 改名 `SMOKE_BASELINES` / `PILOT_BASELINES` | `::test_the_two_baseline_vocabularies_are_named_for_their_datasets` |
| I9 FCF 符号约定不一致 | 已修 | `sec_bulk` 两处改为 `ocf - abs(capex)` | `::test_reported_free_cash_flow_uses_the_absolute_capex_convention` |
| I10 `extraction_reference` 只捕获 `ValueError` | 已修 | `_line`/`_text` 容忍 `None` 与类型错误 | `::test_csv_helpers_tolerate_a_missing_trailing_field` |
| I11 `temporal_trajectories` 遇 `None` 崩溃 | 已修 | 不可计算的 `delta` 置 `None` | `::test_a_trajectory_with_no_computable_delta_reports_none` |
| I12 XBRL 别名表分歧 | 已修 | `sec_bulk.CONCEPT_ALIASES` 由 `xbrl.CONCEPTS` 派生；`DebtCurrent` 提到 `LongTermDebtCurrent` 之前 | `::test_the_bulk_corpus_builds_its_aliases_from_the_online_concept_table` |
| I13 `benchmark_protocol` 失败语义不一致 | 已修 | `fit_decision_stump` 补矩形校验；`calibration_curve` 与 `expected_calibration_error` 对齐校验 | `::test_fit_decision_stump_rejects_empty_and_ragged_matrices`、`::test_calibration_curve_rejects_what_expected_calibration_error_rejects` |
| J3 `export_pdf` 覆盖率最低 | 已修 | 补测试覆盖整个函数（含分页） | `test_audit_coverage_gaps.py::test_export_pdf_writes_a_readable_pdf`、`::test_export_pdf_paginates_a_long_report`；`report.py` 覆盖率 56% → 97% |
| J4 前端只有 4 个测试 | 已修 | 新增 `guards.test.mjs`（5）、`proxy.test.mjs`（9），`presentation.test.mjs` 扩到 12 条；守卫与代理策略抽为可测的 `.mjs` 模块 | `node --test test/*.test.mjs` → **21 passed** |
| J5 7 张空壳表 | 已披露 | `docs/enterprise_platform.md` 新增"持久化现状"章节，逐表说明真实实现；`model_registry` 只写不读单独标注 | `test_migration_wiring_ratchet.py`（3 条）：从迁移与运行时 SQL 字面量机械核验空壳表集合，并断言文档提到每一张，防止该披露随代码漂移 |

## 复查轮（同日）：逐条回看改动时发现并修掉的 4 个问题

对全部改动做了一次对抗性复看（重点在边界情况与"改动是否引入新错误"），发现并修复：

| # | 问题 | 影响 | 修复 |
|---|---|---|---|
| 1 | `_SCALE_PATTERN` 的 `(?![\w,])` 把**词尾逗号**也排除掉了 | `"(In Millions, Except Per Share Data)"`、`"Dollars in Thousands, except share data"` 等最常见的 10-K 表头**不再被识别**，整页按量纲 1 处理，即 1000×/10⁶× **低估**——正是 I4 要修的错误的镜像。原正则（审计前）本来能识别这些 | 边界改为**按分支各自设置**：词 token 只用词边界，`000` 分支额外排除逗号。`parser.py` 抽出 `_scale_token()`；端到端验证 Millions → 1.234e9、Thousands → 1.234e6，且表头里的 `$1,000,000` 不触发放大 |
| 2 | 同上改动若写成非捕获组，`parser.py` 的 `scale_match.group(1)` 会 `IndexError` | 任何带量纲 token 的文档在摄取时直接崩 | 改为两个各自带捕获组的模式 + `_scale_token()` 统一取词，并加测试锁住"每个能返回的 token 都能在 `_SCALE_TOKENS` 里查到" |
| 3 | `decision.py` 里 `contradiction.get("evidence", {})` 有**两处**（只改了一处） | `evidence` 显式为 `None` 时 `AttributeError`——与仓库"`None` 表示缺失"的约定冲突（H4 同类反模式） | 两处统一走已归一化的 `evidence[0]`；三种取值（`None`/`{}`/正常）实测均不再抛错 |
| 4 | `_assert_known_operator` 只覆盖**单条件规则** | 12 条多条件规则的算子从未校验，而 `RuleEngine.evaluate` 把未知算子当作"条件不成立"，于是拼写错误会**静默禁用整条规则** | 校验改为遍历全部 68 条规则的所有条件；注入 `=<` 到 `LIQ_007` 实测在构造期即报错 |

同时确认了几处"看起来可疑但实际正确"的点：`INSTANT_FIELDS` 与旧硬编码集合完全等价（交集无差异）、`BULK_FIELDS` 与旧别名表键一致（无字段丢失）、`selective_metrics` 新增的 `abstained` 键不影响既有消费方、提交版 PDF blob 无 CRLF（未被自动换行破坏）、`FUSION_METHODS` 四个方法的必需参数都在分派表里（不会误报 422）、前端真正调用的 `/api/v1/documents/analyze` 响应满足 `isAssessmentPayload`（实测 200 且守卫通过）。

## 未按报告字面执行、但已说明理由的三处

1. **C3**：没有删除那 25 条规则。它们的条件是正确的，且调用方可通过 `assess(current=...)` 直接提供这些事实使其触发，因此问题是"抽取侧缺失"而非"规则错误"。按报告给出的第二方案（披露有效覆盖面）处理。
2. **`presentation.mjs` 的 `page === 0`**：`FinancialValue.page` 的默认值 0 是"未记录页码"哨兵（PDF 页码从 1 开始），因此 0 被省略是正确行为。改动是把"靠真值隐式判定"变为"显式判定并写明理由"，而不是改成渲染 `page 0`。
3. **I6 的三个算术代理消融**：没有改成真实重跑。真实重跑需要能"去掉某组件"地构造 pipeline，会改变已冻结并对外引用的试点数值，属产品决策。按报告的允许方案（明确标注为算术代理）处理，并把标注做成随数据发布的 `method` 字段而不是仅写在文档里。

## 本轮顺带发现并已披露的一处既存偏差

冻结的 `research/results/public_v1` 是 v0.3.0 口径的产物，**在当前代码下已不可逐字节复现**：`intc-2024/full_hybrid` 风险概率 0.427 → 0.391，`without_trends` 0.340 → 0.283，其余全部一致（已用代码逐行比对确认）。原因是上一轮整改统一了模型映射算子表并移除了 `StopIteration` 路径，改变了 Intel 触发的模型信号。这与报告 J2 记录的 `examples/` 漂移同源。

处理方式：**不改冻结文件**（CI 明确校验其未被重写，且它们是 `research/results.md` / `research/error_analysis.md` 引用的试点口径），改在 `research/results.md` 增加"Reproducibility caveat"小节写明两个具体数值、成因，以及"今天重跑只会得到两个不同的 Intel 数字，不是运行损坏"。

## 已知限制

- **组件级渲染测试仍缺**：报告 J4 要求覆盖 8 个 React 组件。本仓库的前端测试运行器是纯 `node --test`（不编译 TS/TSX），且未安装 jsdom / react-test-renderer，因此无法渲染组件。本轮的做法是把所有可测的纯逻辑（响应守卫、代理策略、展示格式化）抽到 `lib/*.mjs` 并测到，组件侧的崩溃路径改为**防御式取值 + 局部错误边界**（`PanelBoundary`）双保险，并以 `next build` 的类型检查兜底。若要真正做组件测试，需要引入测试渲染器并更新 `package-lock.json`，属独立变更。
- **PostgreSQL 路径本地跳过**：`tests/test_postgres_runtime.py` 的 3 个用例需要 `DATABASE_URL`（CI 提供 PostgreSQL 服务），本地显示为 3 skipped。本轮新增的 `save_case_transition` 比较交换用例即在此文件中，CI 会执行。

## 门禁前后对比

| 项目 | 整改前 | 整改后 |
|---|---|---|
| `ruff check backend tests scripts` | 通过 | 通过 |
| `pytest` | 208 passed / 2 skipped | **362 passed / 3 skipped** |
| 覆盖率 | 92% | **93.47%** |
| `tsc --noEmit` | 通过 | 通过 |
| `next build` | 成功 | 成功 |
| 前端 `node --test` | 4 passed | **21 passed** |
| `git diff --check` | 干净 | 干净 |
| 冻结产物（`research/results/public_v1`、`v0.3.1`） | 未改动 | 未改动（`replay_frozen_experiment.py` 逐文件哈希校验一致） |

## 第二轮深度复核（2026-09-15）

在第一次整改基础上，又逐项回看了财务公式、策略边界、研究指标、并发更新、文档超时和前端消费契约。新增修复如下：

- **财务计算**：利息保障倍数统一使用 `EBIT / abs(interest_expense)`，兼容报表中费用为负数的符号约定；利率压力情景按原符号增加利息成本绝对值；NaN、Infinity、布尔值不会再进入比率、模型和基准计算。
- **数字解析**：表格行提取不再把欧式 `1.234,56` 拆成两个数字；美式与欧式千分位/小数格式均有端到端测试。
- **策略与融合**：拒绝空策略、未知字段、拼错的方向/阈值名、非有限数、反向 warning/critical 阈值、负权重及次序颠倒的决策阈值，消除比较结果为 false 后的静默放行。
- **决策完整性**：人工审查可把 PASS/FLAG 收紧为 REVIEW，但不能把证据不足导致的 ABSTAIN 放宽；矛盾原因码必须属于闭合枚举。
- **研究口径**：零条可核验 claim 时，unsupported/verified rate 改为 `null`（分母不存在），不再虚构 100% 不支持；不产生叙事 claim 的数值基线不再继承 Full Hybrid 的 claim 指标。
- **并发与存储**：风险案例更新的 CAS 同时比较状态与 `updated_at`，覆盖“同状态并发修改”；Windows 保留设备名及尾随点路径被拒绝。
- **超时与前端**：文档分析超时后由工作线程持有并最终清理临时 PDF，避免请求线程提前删除仍在读取的文件；前端代理的分析超时上调到 125 秒，与浏览器 120 秒契约一致；响应守卫检查完整数组及关键嵌套结构，且新分析会重置局部错误边界。
- **宿主兼容性**：日志初始化不再清空宿主应用已有 handler；告警、校准、治理比较和基准训练统一拒绝 NaN/Infinity、布尔伪数字、越界概率和未知策略键。

上述更改不改写冻结研究产物。验证统计以本轮最终门禁实际输出为准；PostgreSQL 集成仍只有在提供 `DATABASE_URL` 或可用容器服务时才能本地执行，不能把 skipped 误称为通过。
