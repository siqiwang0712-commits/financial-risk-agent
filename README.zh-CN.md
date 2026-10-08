<div align="center">

<img src="docs/assets/finrisk-guardian-logo.png" alt="FinRisk Guardian 项目 Logo" width="180" />

<img src="docs/assets/finrisk-platform.svg" alt="FinRisk——以证据为基础的金融风险智能平台" width="100%" />

# FinRisk

### 受保证的选择性金融智能——v0.4.2

[![CI](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/workflows/ci.yml)
[![Python 3.11–3.12](https://img.shields.io/badge/Python-3.11%E2%80%933.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-d45b3e)](LICENSE)

**一个把金融风险预测与决策授权明确分开的研究系统。**

[English](README.md) | 简体中文

当前发布元数据：**v0.4.2 · 2026-10-08** ·
[发布说明](RELEASE_NOTES_v0.4.2.md) · [安全与验证记录](docs/SECURITY_HARDENING_v0.4.2.md)

v0.4.2 是安全与可靠性补丁。实际发布是独立的维护者操作；v0.4.1 历史研究证据
保持不变，FinRisk 仍为 UNCALIBRATED，E5 仍被阻塞且未冻结。

[快速开始](#快速开始) · [工作原理](#工作原理) ·
[研究概览](#研究概览) · [文档导航](#文档导航)

</div>

> [!IMPORTANT]
> **FinRisk 是研究原型。** v0.4 已实现 Assurance Runtime，但实现本身并不等于外部验证。
> 其 0–100 风险指数是专家设计且尚未校准
>（`UNCALIBRATED`）的启发式指标，不是破产概率、信用评级、舞弊认定或投资建议。
> 本项目不声称已完成生产部署、外部验证、监管批准，也不承诺生产 SLA。

## 什么是 FinRisk？

FinRisk 是一个开放的金融风险研究系统，用于分析财务恶化信号，并判断一个候选结论是否获得
了足够支持、可以正式输出。
它把结构化 SEC/XBRL 数据和年报 PDF，与确定性财务指标、传统筛查模型、版本化专家规则，
以及用于解读叙述性披露的受约束大语言模型结合起来。

模型、规则、融合和 Agent 推理只能生成 `proposed_decision`（候选决策），无权自行发布最终
决策。独立的 Assurance Runtime 会检查已验证证据、单项证据脆弱性、参考分布有效性、模型
分歧、校准状态和策略成熟度。只有合法且受哈希保护的 `AssuranceResult` 才能产生
`final_decision` 和可重放的 Decision Certificate。

这就是 v0.3.x 到 v0.4 的变化：v0.3.x 提供以证据为基础的风险分析；v0.4 把决策授权提升为
独立且失败关闭的运行时层。风险严重度、证据支持度、脆弱性、分布有效性、模型分歧和校准
状态保持分离。

### v0.4.1 新增了什么？

v0.4.1 围绕上述架构完成研究准备与发布加固：新增仅用于研究的 StrongTabularReference-v1、
已批准的历史开发数据、明确区分 V/O/VO/CC 的可观测性诊断、经验开发参考分布、选择性评估
工具和分阶段 E5 预检。同时加固上传准入、数值证据来源、非法 Assurance 状态拒绝，以及
受证书约束的授权展示。软件发布不等于前瞻或外部验证；E5 仍受阻，尚未冻结。

## 为什么需要 FinRisk？

年报、10-K 和 20-F 的关键证据分散在 XBRL 事实、财务报表、附注、管理层讨论与分析
（MD&A）、风险因素和审计措辞中。可信的评估需要统一期间、单位和重述口径，稳定计算指标，
用数据检验管理层叙述，并保留可追溯的来源链。

不受约束的大语言模型并不适合充当金融风险裁判。它可能抄错列、丢失单位、自行编造计算、
轻信乐观叙述，或给出证据不足的结论。FinRisk 将职责交给更适合的系统组件：

| 职责 | 负责组件 |
|---|---|
| 权威数值、单位、期间和重述 | XBRL 摄取与确定性标准化 |
| 比率、趋势、情景和模型公式 | 经过测试的确定性工具 |
| MD&A、附注和审计措辞的解释 | 受 JSON Schema 约束的大语言模型 |
| 风险模式与阈值 | 版本化规则与策略 |
| 风险分数、严重度与候选处置 | 规则、模型、融合和 Agent 推理 |
| 最终决策授权 | 仅限 Assurance Runtime |
| 不可变决策记录 | Decision Certificate |

> **预测组件可以提出金融风险决策；只有 Assurance 层可以授权最终决策。**

## 工作原理

<img src="docs/assets/assurance-architecture.svg" alt="FinRisk v0.4 保证控制架构" width="100%" />

```text
财务报告
    ↓
摄取 / 标准化
    ↓
指标 / 规则 / 模型 / 受约束 LLM / Agent
    ↓
风险融合 → 候选决策
    ↓
Decision Assurance Runtime
  证据 · 脆弱性 · 分布有效性 · 准入策略
    ↓
PASS / FLAG / REVIEW / ABSTAIN
    ↓
Decision Certificate
```

运行时形成四个明确的职责边界：

1. **接口层（Interface Layer）**——FastAPI 与 Next.js Workbench 负责展示输入、流程和证据，
   不执行金融风险计算。
2. **预测层**——确定性工具和受约束 Agent 推理计算金融信号并提出候选处置，但没有最终授权权。
3. **Assurance 层**——证据保证、确定性消融、分布有效性诊断和版本化策略决定授权、限制或拒绝。
4. **证书层**——把输入/文档摘要、组件版本、候选决策、保证结果、最终决策和重放信息写入内容哈希证书。

`FinRiskPipeline` 仍是 API、Agent 与工具注册表共享的计算所有者；`AssuranceEngine` 是唯一的
授权所有者。系统强制执行：`没有有效的 AssuranceResult，就没有已授权的 final_decision`。

详见[v0.4 Assurance 架构](docs/assurance_architecture.md)、
[完整架构与平台边界](docs/enterprise_platform.md)、
[三层迁移图](docs/three_layer_migration.md)和
[决策级控制](docs/decision_grade_controls.md)。

## 核心能力

- 摄取 SEC Company Facts 和 inline XBRL，并保留申报文件、期间、单位、分类体系、accession
  与重述来源。
- 对年报 PDF 进行页级分析，并通过有界、可终止的进程执行昂贵任务。
- 进行跨来源核对，不静默取平均，也不把缺失值替换为零。
- 计算流动性、杠杆、盈利、现金流、营运资金和多期趋势。
- 运行 Altman Z、Beneish M、Piotroski-style F 与 Ohlson O，并执行适用性检查。
- 评估 68 条版本化专家规则，包括可检查的单因素和交叉因素信号。
- 通过类型化 Agent 完成规划、工具调用、交叉核验和候选决策，但 Agent 无授权权。
- 验证引文、跟踪证据状态，并构建从来源到决策的来源图。
- 对证据进行确定性消融，报告分数影响、决策翻转及受影响结论。
- 生成精确或明确标注为近似的 Decision-Sufficient Evidence Set。
- 以保守的分布有效性状态在参考条件之外失败关闭。
- 把财务值与报告可观测性分开；缺失模式不得静默抬高金融严重度。
- 保存不可变 Decision Certificate，执行确定性重放和哈希完整性核验。
- 在覆盖不足、证据矛盾、模型分歧、组件不可用或输入无效时明确进入
  `REVIEW` / `ABSTAIN`。

准确的“已实现 / 部分实现 / 未实现”清单维护在
[项目状态](PROJECT_STATUS.md)与[能力成熟度矩阵](docs/capability_maturity_matrix.md)中。

## API 概览

后端提供健康/就绪检查、确定性与 Agent 评估、PDF 与 XBRL 分析，以及按租户隔离的实体、
风险案例、策略、快照、时序风险、情景、融合和审计事件接口。受保护的接口使用
`X-API-Key`；组织和角色由服务端保存的哈希凭据解析，不信任调用方自报的角色头。

评估响应明确区分 `risk_score`、`risk_severity`、`proposed_decision`、`assurance`、
`final_decision` 与 `decision_certificate`。验证、限流、数据存储和文档处理均采用失败关闭策略，错误会保留关联 ID。全部端点、上传限制、
错误契约和首次引导规则见[完整 API 参考](docs/API_REFERENCE.md)。后端运行后，可在
`http://localhost:8000/docs` 查看交互式 OpenAPI 文档。

## 快速开始

源码运行前提：Python 3.11 或 3.12、Node.js 22+、npm 10+；Docker Desktop 可选。

### Docker

最短的开发启动方式会在本机构建整个栈：

```bash
docker compose up --build
```

Workbench 位于 `http://localhost:3000`，API 位于 `http://localhost:8000`。

使用维护者发布的镜像时，可通过 `docker-compose.release.yml` 启动，并固定到实际发布运行的
镜像摘要。已审计的 v0.4.1 容器运行是未发布的 dry-run，不代表 v0.4.1 镜像发布标签已经存在：

```bash
cp .env.release.example .env    # 编辑密钥和首次引导设置
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

首次管理员创建、PostgreSQL 密码生命周期、secret 文件、健康检查、TLS、镜像摘要固定和 GitHub
attestation 验证均在[容器发布与部署指南](docs/CONTAINER_RELEASE.md)中说明。使用发布栈前，
务必先阅读首次引导顺序。

### 本地开发

后端：

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn finrisk.api:app --reload
```

在另一个终端启动前端：

```bash
cd frontend
npm ci
npm run dev
```

存活检查位于 `http://localhost:8000/health/live`，就绪检查位于
`http://localhost:8000/health/ready`。

### 离线合成演示

```powershell
$env:PYTHONPATH="backend"
python scripts/run_demo.py
```

附带的公司样本被明确标记为 `synthetic`。它只验证运行机制，不代表真实世界表现。研究核验与
SEC 源数据获取见[可复现性指南](research/EXPERIMENT_REPRODUCIBILITY.md)。

## 研究概览

### v0.4.1 回顾性开发参考模型

v0.4.1 新增可复现、仅用于研究的 `StrongTabularReference-v1`。在**设计已暴露**且标签
可得性具有选择性的 E4-S 开发子集（675 条观测 / 675 家公司、235 个事件和 440 个非事件）上，预先规定的流程机械选择了
`VO` + Histogram Gradient Boosting。其折外**回顾性开发** AUROC 为 **0.881789**，
PR-AUC 为 **0.828968**。这些不是独立验证估计。分数仍为 `UNCALIBRATED`，不能授权决策，
也没有接入生产评分路径。

可观测性诊断的 AUROC 分别为：财务值 `V` 0.872060、仅报告可观测性 `O` 0.835933、
显式组合 `VO` 0.881789，以及 154 条完整案例敏感性子集 `CC` 0.676736。CC 仅含 10 个
事件，因此只是小样本敏感性结果，不能与全队列估计直接比较。报告可得性在该历史队列中
携带回顾性预测信息，但这不是因果结论，也不是财务严重程度。详见
[规范结果](research/strong_tabular_reference/artifacts/canonical_results.json)、
[诊断报告](research/strong_tabular_reference/OBSERVABILITY_DIAGNOSTIC.md)和
[v0.4.1 发布说明](RELEASE_NOTES_v0.4.1.md)。

E4-S 源队列的全部 2,000 家公司必须从未来 E5 中排除。E5 仍为
`BLOCKED / DRAFT_NOT_FROZEN`：不存在未来队列、预测、结果或冻结身份。

原始 E4 证据来自锁定的 v0.3.4 实现及其明确标注为事后分析的审计。E4 的 674 个可核验结果
与上述 E4-S 的 675 条开发观测是不同的历史对象。更早的 pilot 和 v0.3.1 产物仍保留为历史审计记录。

| E4 结果 | 数值 |
|---|---:|
| 冻结且公司互斥的 FY2024 队列 | 2,000 家公司 |
| 可由确定性规则核验的结果 | 674（其中 235 个事件） |
| B0 仅比率基线 AUROC | 0.678（95% CI 0.633–0.721） |
| B6 时序风险 AUROC | 0.708（95% CI 0.663–0.750） |
| 配对 B6 − B0 ΔAUROC | +0.030（95% CI +0.014 至 +0.048） |

在 E4 可确定性核验的子集上，B6 优于 B0。终点是财务恶化，而非破产、违约、信用损失或
资不抵债概率；可核验结果仅覆盖冻结队列的 33.7%。

后续研究进一步收紧了结论边界：

- **E4-S 统计审计：** 正确设定的配对检验支持相同方向，但 E4 已发表的标签置换 p 值检验的
  原假设，与其文字所述的“两个模型相等”并不一致。审计重跑队列与 E4 约有 94% 重叠，属于
  近似复现，不是独立样本。
- **E4-R 稳健性研究：** 在 E4-S 的 675 条复现队列上，B6 AUROC 为 0.705，预先指定的非线性
  表格模型挑战者为 0.885。强学习基线明显优于 B6；其中相当一部分优势来自报告与缺失模式，
  且该分析仍属于事后研究。
- **Agent 与 Hybrid 结果：** E4 的完全配对比较只有 5 个可核验事件，因此尚未证明 Agent 或
  Hybrid 的增量价值。事后的 Codex 比较器不会改变这一边界。

所有系统仍为 `UNCALIBRATED`。现有研究没有证明总体人群表现、全文档 Agent 有效性、概率校准、
生产适用性或监管有效性。

建议从[实验总览](research/EXPERIMENT_OVERVIEW.md)和
[实验结果](research/EXPERIMENT_RESULTS.md)开始。完整方法与限制见
[E4 验证报告](research/e4/public/VALIDATION_REPORT.md)、
[E4-S 审计](research/e4_statistical_audit/AUDIT_REPORT.md)、
[E4-R 最终报告](research/e4r_automated_robustness/FINAL_REPORT.md)和
[研究限制](research/limitations.md)。

## 项目状态与成熟度

**v0.4.1——Research Readiness & Strong Reference** 于 **2026-10-05 发布**。
Assurance 权威边界、确定性证据脆弱性、决策充分证据、分布有效性诊断和 Decision Certificate
已经实现。这是研究原型的软件发布：它没有修改冻结的 E4 结果，没有证明前瞻预测优势，也没有冻结或运行 E5。

- **在有限研究范围内已验证：** 确定性样例、自动质量门槛、冻结 E4 产物完整性，以及 B6 相对
  B0 在 674 个可核验 E4 结果上的改进。
- **内部开发验证已完成：** Assurance 权威边界、证据保证、确定性脆弱性、充分证据搜索、
  有效性状态、证书哈希、重放集成、API 契约、Workbench 层级、Python 3.11/3.12、
  可安装产物，以及 Docker/PostgreSQL 重启持久性。
- **仅限开发参考：** 一个带哈希的合成 profile 可复现地覆盖 `IN_REFERENCE`、`WARNING`
  和 `OUTSIDE_REFERENCE`。v0.4.1 另增不使用标签构建的
  `EMPIRICAL_DEVELOPMENT_REFERENCE_ONLY` 研究 profile；两者都不是外部验证参考，
  未知真实输入仍按失败关闭处理。
- **已实现但未外部验证：** XBRL/PDF 核对、时序状态、受约束 provider、Agent critic/verifier、
  风险案例流程、RBAC/API key 与存储。
- **待完成：** 前瞻性 E5、E5 冻结的参考分布设计、校准准入策略、外部验证及生产/监管评估。

[项目状态](PROJECT_STATUS.md)是成熟度的权威清单。发布范围与历史见
[v0.4.1 发布说明](RELEASE_NOTES_v0.4.1.md)和[变更日志](CHANGELOG.md)。
[最终工程审计](docs/RELEASE_AUDIT_v0.4.1.md)记录了已测试的运行时代码 SHA、通过的 CI 与
容器 dry-run，以及本地环境限制。

## 仓库结构

```text
backend/      核心后端、确定性工具、企业服务和 Agent
frontend/     Next.js 分析师 Workbench
config/       评分、模型和策略配置
docs/         架构、部署、API、控制与工作流文档
research/     协议、冻结产物、验证、审计和限制
rules/        68 条版本化专家规则与明确的禁用规则登记表
tests/        单元、安全、重放和集成测试
scripts/      演示、核验、基准与数据构建工具
examples/     明确标记为合成的样例和示例报告
failure_lab/  注入故障目录及预期的失败关闭行为
```

## 安全与治理

- 组织范围的 repository 查询和服务检查用于执行租户边界。
- 企业 API 凭据在服务端以哈希形式保存；不信任调用方提供的角色头。
- 人工 override 会保留原决策、新决策、执行人、原因和时间。
- 正式运行会记录模型、prompt、规则、融合和策略版本。
- 风险案例进入 Accepted 或 Resolved 前，必须具有服务端核验过的证据路径。
- 凭据、`.env` 文件、私有报告、上传文件、缓存和生成的评估不会进入版本控制。

这些是研究原型中的已实现控制，不是认证声明。部署前请阅读完整的
[威胁模型与就绪边界](docs/decision_grade_controls.md)、
[企业平台边界](docs/enterprise_platform.md)和
[可复现性与运行时完整性指南](docs/reproducibility_runtime_integrity.md)。

## 文档导航

### 理解 FinRisk

- [v0.4 Assurance 架构](docs/assurance_architecture.md)
- [架构与企业边界](docs/enterprise_platform.md)
- [项目状态](PROJECT_STATUS.md)
- [决策级控制、治理与威胁模型](docs/decision_grade_controls.md)
- [三层迁移图](docs/three_layer_migration.md)
- [能力成熟度矩阵](docs/capability_maturity_matrix.md)
- [Intel FY2024 证据链案例](docs/case_study_001.md)

### 运行 FinRisk

- [容器发布与部署](docs/CONTAINER_RELEASE.md)
- [可复现性与运行时完整性](docs/reproducibility_runtime_integrity.md)
- [实验复现](research/EXPERIMENT_REPRODUCIBILITY.md)
- [v0.4 内部开发验证](research/v040_development/VALIDATION_REPORT.md)
- [风险案例工作流](docs/risk_case_workflow.md)
- [时序风险智能](docs/temporal_risk_intelligence.md)

### 研究

- [实验总览](research/EXPERIMENT_OVERVIEW.md)
- [实验结果](research/EXPERIMENT_RESULTS.md)
- [评估协议](research/evaluation_protocol.md)
- [错误分析](research/error_analysis.md)
- [限制](research/limitations.md)
- [E4-S 统计审计](research/e4_statistical_audit/AUDIT_REPORT.md)
- [E4-R 稳健性研究](research/e4r_automated_robustness/FINAL_REPORT.md)
- [人机协作研究协议](research/human_ai_study_protocol.md)
- [E5 草案——受保证选择性决策的前瞻验证](research/e5/README.md)

### 开发

- [API 参考](docs/API_REFERENCE.md)
- [贡献指南](CONTRIBUTING.md)
- [变更日志](CHANGELOG.md)
- [v0.4.1 发布说明](RELEASE_NOTES_v0.4.1.md)
- [v0.4.1 最终工程审计](docs/RELEASE_AUDIT_v0.4.1.md)
- [v0.4.0 发布说明](RELEASE_NOTES_v0.4.0.md)
- [v0.3.4 发布说明](RELEASE_NOTES_v0.3.4.md)
- [Failure Lab](failure_lab/README.md)

## 限制

FinRisk 是研究原型。它：

- 尚未校准（`UNCALIBRATED`），不是破产、违约或判断正确性的概率；
- 当前 Assurance 策略仍是启发式策略，不是已校准的选择性风险保证；
- 不能断言已经获得外部验证的分布有效性；仓库内合成参考明确标记为
  `DEVELOPMENT_REFERENCE_ONLY`，历史经验研究参考为 `EMPIRICAL_DEVELOPMENT_REFERENCE_ONLY`，
  不是 E5 冻结参考，也不是生产参考；
- 不是信用评级、舞弊认定或投资建议；
- 不能证明可核验研究子集之外的总体人群表现；
- 不是对重大金融决策进行人工复核的已验证替代品；
- 尚未针对生产、监管或安全关键用途完成外部验证。

风险严重度、证据覆盖率、证据质量、模型分歧、可靠性和概率是不同概念，FinRisk 不会把它们
混为一谈。规则、权重、融合阈值和证据覆盖置信度没有经过外部校准，全文档 Agent 验证也尚未
完成。

选择偏差、右删失、缺失模式、机器复核、模型适用人群和可复现性边界见完整的
[研究限制](research/limitations.md)。

## 参与贡献

欢迎贡献。修改财务公式时，需要补充边界条件测试和一手资料依据。新增规则必须具有稳定 ID、
类别、严重度、明确条件、有界影响，并完成重复性检查。合成样例必须标记为 `synthetic`。

完整规范和核验命令见[贡献指南](CONTRIBUTING.md)。

## 许可证

项目采用 [Apache License 2.0](LICENSE)。

---

<div align="center">

**预测负责提出。Assurance 负责授权。证据始终可检查。**

<sub>FinRisk 研究金融 AI 应当自动化什么、必须验证什么，以及哪些决策必须由人作出。</sub>

</div>
