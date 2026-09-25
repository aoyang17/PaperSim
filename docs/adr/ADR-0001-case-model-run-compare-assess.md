# ADR-0001：PaperSim 的五个核心原语

- 状态：已接受
- 日期：2026-09-17
- 决策范围：`PaperSim`
- distribution/import：`papersim`
- 主入口：`from papersim import Engine`
- 旧仓库：`/path/to/legacy-paper-engine`，只作为迁移来源
- 关联文档：`../MIGRATION_INVENTORY.md`

## 1. 目标

PaperSim 只做一件事：

```text
论文
-> 建立模型
-> 仿真复现
-> 与论文结果比对
-> 质疑并修改模型
-> 再仿真和再比对
-> 给出模型可靠性判断
```

最终只有两个交付物：

1. 论文原始模型的仿真复现；
2. 论文模型在测试范围内的可靠性判断。

任何功能如果不能直接推动这两个交付物，都不属于 core。

## 1.1 目录拓扑硬约束

PaperSim 采用扁平目录。目录拓扑属于架构约束，不是风格偏好。

计数约定：

- 从项目根或 workspace 根开始计数；
- 子文件夹层级不得超过 2；
- 任何目录的直属子文件夹数量不得超过 3；
- 文件数量不受此限制；
- 新功能不得通过增加目录层数解决；
- 如果对象数量增长，使用文件名、稳定 ID、JSON 引用或 artifact manifest，而不是继续创建类型目录和版本目录。

### 源代码

源代码必须保持扁平：

```text
PaperSim/src/papersim/
├── __init__.py
├── engine.py
├── records.py
├── store.py
├── model.py
├── run.py
├── compare.py
├── assess.py
├── contracts.py
├── comsol.py
└── cli.py
```

禁止：

```text
src/papersim/adapters/comsol/remote.py
src/papersim/domain/model/version.py
src/papersim/application/run/submit.py
```

`src/papersim/` 下不再创建 `adapters/`、`domain/`、`application/`、`services/` 等按架构分层的目录。不同职责通过模块名和接口区分。

`comsol.py` 只实现通用 COMSOL adapter，包括模型打包、远程命令编排和 artifact verification。具体网关连接、实例选择、上传、Slurm 提交和本地环境由用户注入的 `RemoteExecutor` 提供；仓库只保留 `examples/mvp/yeesuan_comsol/` 作为可替换样例。

### MVP examples

站点相关集成不进入 `skills/` 或库源码，只保存在 examples：

```text
PaperSim/examples/mvp/yeesuan_comsol/
├── README.md
├── adapter.py
├── yeesuan_executor.py
├── workflow.md
└── assets/
```

### Workspace

Workspace 根目录只允许三个子目录：

```text
PaperSimWorkspace/
├── objects/
├── artifacts/
└── tmp/
```

这三个目录内部只放文件，不再创建子目录。

对象通过文件名编码类型和 ID：

```text
objects/case_kobayashi1993.json
objects/model_m0001.json
objects/run_r0001.json
objects/compare_c0001.json
objects/assess_a0001.json
```

大文件、输入和 solver artifact 统一放入 `artifacts/`，通过 SHA-256 或稳定 ID 与对象 JSON 关联。需要保留目录形态的数据必须打包成单个归档文件，不能展开成多层目录。

### 原文

`paper/original/` 内部只允许文件，不允许子目录：

```text
PaperSimWorkspace/paper/original/
├── index.json
├── Kobayashi1993A__modeling-and-numerical-simulations-of-dendritic-crystal-growth.pdf
└── ...
```

## 2. 最小流程

```text
Case
  -> Model
  -> Run
  -> Compare
  -> Model
  -> Run
  -> Compare
  -> Assess
```

`Model` 可以反复迭代。`Run` 和 `Compare` 一旦产生就不覆盖。`Assess` 查看整条迭代链，给出最终判断。

## 3. 五个对象

PaperSim 只保留五个对象。

### 3.1 Case

一次论文复现任务。

```text
Case
- id
- paper metadata
- paper_ref
- reference observations
- model ids
- run ids
- compare ids
- assess ids
```

`paper_ref` 不再指向 case 内的私有 PDF 副本，而是指向统一原文仓库中的不可变论文记录。

论文、来源和论文报告的结果观测都属于 `Case`，不再分别建立 `Paper`、`SourceArtifact`、`Observation` 等根对象。

### 3.2 Model

一个不可变的模型版本。

```text
Model
- id
- lineage_id
- parent_id
- model.md
- model.spec.json
- change_reason
- created_by
- created_at
```

`model.md` 是自然语言模型，允许持续扩充公式、假设、推导和解释。

`model.spec.json` 是同一 Model 的机器可读视图，至少包含：

- variables
- governing equations
- constitutive equations
- parameters and units
- initial and boundary conditions
- assumptions
- solver settings supplied by the paper
- output quantities used for comparison
- evidence references

`model.spec.json` 允许是不完整的。论文没给出、复现又必需的部分，必须标记为 `assumption` 或 `gap`。

`Equation`、`ConstitutiveEquation`、`Parameter`、`InitialCondition`、`BoundaryCondition` 和 `Assumption` 是 `model.spec.json` 内的结构，不是独立根对象。

### 3.3 Run

一次不可变的仿真执行。

```text
Run
- id
- model_id
- solver
- solver_version
- environment
- status
- inputs
- logs
- artifacts
- metrics
```

`SimulationPlan`、`RunArtifact` 和 `ReproductionResult` 都折叠进 `Run`。

### 3.4 Compare

一次“论文观测 vs 仿真结果”的比对。

```text
Compare
- id
- run_id
- observation ids
- metrics
- mismatches
- uncertainty
- evidence references
- interpretation
```

`Mismatch`、`MismatchDiagnosis` 和 error metric 都作为 `Compare` 内的字段，不单独建对象。

### 3.5 Assess

对一条模型迭代链的可靠性判断。

```text
Assess
- id
- case_id
- model_ids
- run_ids
- compare_ids
- verdict
- findings
- confidence
- scope
- unresolved questions
```

`Challenge`、`FalsificationTest`、`AlternativeModel`、`ModelVariant` 和 `Finding` 不建立独立类型，分别收进 `Model.change_reason`、`Compare.mismatches` 和 `Assess.findings`。

最终 verdict：

```text
supported
qualified
questioned
not_reproduced
underdetermined
```

## 4. 原文仓库、Markdown 与 Model 版本

### 4.1 原文统一存放

以后所有论文原文统一存放在：

```text
/path/to/PaperSimWorkspace/paper/original/
```

目录结构约定为：

```text
PaperSimWorkspace/paper/original/
├── index.json
├── Kobayashi1993A__modeling-and-numerical-simulations-of-dendritic-crystal-growth.pdf
└── ...
```

规则：

- `paper/original/` 是论文原文的唯一 canonical location；
- case 内不得再保存一份会被当作原文使用的 PDF 副本；
- `Case.paper_ref` 保存 `paper_id`、文件路径和 SHA-256；
- `index.json` 保存 `paper_id`、title、authors、year、DOI、bibkey、filename、sha256 和 added_at；
- 原文文件加入后不得修改或覆盖；
- 相同 SHA-256 的论文不得重复登记；
- 文件名采用 `<paper_id>__<safe-title>.<ext>`，登记后保持稳定；
- parser、page image、Markdown 和 source map 属于派生 artifact，不写入 `paper/original/`；
- 如果论文来自 DOI、URL 或外部库，也先解析成原文文件并登记到 `paper/original/`，再创建或关联 Case。

`paper/original/` 是 PaperSim 中明确允许保存 source corpus 的位置；其他用户数据、run、model、compare 和 assess 仍进入 `PaperSimWorkspace`。

### 4.2 Markdown 与 Model

模型可以使用持续扩充的 Markdown：

```text
model.md
```

规则：

- `lineage_id` 是稳定模型身份；
- 每次修改产生新的 `Model.id`；
- 旧 Model 永不覆盖；
- 每个 `Run` 绑定一个不可变 `Model.id`；
- 修改 Markdown 后必须重新生成 `model.spec.json`；
- 如果 Markdown 已变化但 spec 未更新，该 spec 标记为 `stale`；
- baseline 永远指向当时的 Model，不跟随后续修改。

因此 API 中的 `model.id` 可以直接使用：

```python
run = engine.run(model.id, backend="comsol")
```

这里的 `model.id` 是 version-specific immutable id，不是会随 Markdown 变化的“最新版本”指针。

## 5. 五个操作

`Engine` 只暴露主链操作：

```python
case = engine.case(
    "/path/to/PaperSimWorkspace/paper/original/Kobayashi1993A__modeling-and-numerical-simulations-of-dendritic-crystal-growth.pdf"
)

model = engine.model(case.id, agent=model_agent)

baseline = engine.run(model.id, backend="comsol")

compare = engine.compare(
    run=baseline.id,
    case=case.id,
)

revised = engine.model(
    case.id,
    parent=model.id,
    compare=compare.id,
    agent=model_agent,
)

variant_run = engine.run(revised.id, backend="comsol")

assess = engine.assess(case.id, agent=assessor)
```

主操作只有：

```text
case
model
run
compare
assess
```

没有单独的 search、screen、read、challenge、extract、report、publish 或 revise API；Model 迭代通过 `engine.model(parent=...)` 完成。

## 6. 状态规则

Case 状态可以不存为复杂 workflow，直接由五个对象是否存在推导：

```text
has_case
has_model
has_run
has_compare
has_assess
```

规则：

- 没有 baseline run，不能给出 reliability verdict；
- 没有 Compare，不能生成 Assess；
- baseline 和所有 variant run 都永久保留；
- failed run 可以存在，但不能作为 baseline；
- 模型修改必须产生新的 `Model.id`；
- Assess 必须列出它查看过的 Model/Run/Compare；
- 任何补全的 assumption 必须单独标记，不能写入“论文原始模型”。

### 6.1 成果标准化控制

所有 Case、Model、Run、Compare、Assess 的成果必须标准化。标准化不是文档规范，而是机器可验证的契约。

控制机制分为六层：

1. **统一 envelope**：每个对象都有 `schema_version`、`id`、`created_at`、`producer`、`refs`、`status` 和 artifact hash。
2. **对象 schema**：五个对象各有 JSON Schema，缺字段、类型错误、枚举错误一律拒绝。
3. **阶段 validator**：每个对象进入 canonical store 前必须通过独立 validator。
4. **状态门禁**：缺少上游对象或校验失败时，Engine 不允许进入下一阶段。
5. **contract tests**：每个对象至少有一组正例和一组必须失败的反例。
6. **schema version/migration**：schema 变化必须显式升级版本，不能静默改变字段含义。

阶段门禁固定为：

```text
Case
  paper_ref 存在
  source SHA-256 与 index.json 一致
  metadata 通过 schema

Model
  model.md 存在
  model.md 含标准章节
  model.spec.json 存在
  equations/parameters/conditions/gaps 通过 schema
  assumptions 与 paper facts 已区分

Run
  model_id 存在且不可变
  solver/version/environment 已记录
  run 状态和退出码可验证
  log 和 artifact hash 存在

Compare
  run_id 和 reference observation 存在
  metrics 通过 schema
  mismatch 和 uncertainty 已标记

Assess
  baseline 和 edition chain 存在
  acceptance 已逐条评估
  verdict 使用固定枚举
  scope 和 unresolved questions 已填写
```

`model.md` 允许持续扩充自然语言公式，但必须使用固定章节骨架，例如：

```text
# Model
## Scope
## Variables
## Governing Equations
## Constitutive Equations
## Parameters
## Initial Conditions
## Boundary Conditions
## Assumptions
## Solver Mapping
## Outputs
## Evidence
## Open Gaps
## Change Log
```

`model.md` 是自然语言 artifact，`model.spec.json` 是经过校验的机器视图。Markdown 修改后生成新的 Model，并重新校验 spec。未重新生成或校验的 spec 标记为 `stale`。

统一控制规则：

- Agent 只提交 draft，不直接写 canonical object；
- Engine 是唯一 canonical writer；
- 所有 validator 失败必须返回结构化错误；
- 不能通过空字符串、`null`、占位文件或“稍后补充”绕过门禁；
- 每个 artifact 进入 canonical store 前必须计算 hash；
- 对象被下游引用后不可原地修改；
- JSON 是机器接口，Markdown 只用于 Model 解释和证据承载；
- 任何阶段的 reviewer/Agent 结论都必须写成相同 schema，而不是自由文本。

## 7. Agent 接口

PaperSim 不实现 Agent 框架，只定义任务接口。

```python
class AgentAdapter(Protocol):
    def capabilities(self) -> set[str]: ...
    def run(self, task: AgentTask) -> AgentResult: ...
```

最小 capability：

```text
model
compare
assess
```

可选 capability：

```text
case
```

边界：

- Agent 输入和输出使用 PaperSim 的 typed artifact；
- Agent 不能直接修改 canonical state；
- Engine 负责 schema、单位、evidence、状态和 Model version 校验；
- 不同 Agent 可以替换同一个 task；
- 是否使用多 Agent、如何审阅、由谁调用，属于上层策略；
- PaperSim 不内置 Agent 编排产品。

### 7.1 当前 Agent 作为第一个候选

当前正在使用的 Agent 作为第一个 `AgentAdapter` candidate：

```text
current_agent
```

用途：

- 从 `paper/original/` 中的原文生成 `Case` metadata 和 reference observations draft；
- 协助生成 `model.md` 和 `model.spec.json`；
- 阅读 `Compare` 结果并诊断 mismatch；
- 提出新的 Model revision；
- 生成 `Assess` findings、verdict 建议和 unresolved questions；
- 在需要时按 `yeesuan-comsol` skill 执行远程 COMSOL 建模、提交和验证。

约束：

- current Agent 只能提交 draft；
- Engine 负责验证、版本化和写入 canonical state；
- Agent 不得直接覆盖原文、Model、Run 或 Compare；
- Agent 必须使用明确 task，不得依赖隐式聊天历史作为证据；
- Agent 的输出必须区分 paper fact、extracted fact、inference 和 assumption；
- 后续可以替换为其他 AgentAdapter，而不改变 Case/Model/Run/Compare/Assess。

### 7.2 Agent 选择与库解耦

PaperSim 库不内置任何具体 Agent。库只在 `contracts.py` 定义：

```python
class AgentAdapter(Protocol):
    def capabilities(self) -> set[str]: ...
    def run(self, task: AgentTask) -> AgentResult: ...


class SolverBackend(Protocol):
    def validate(self, model): ...
    def build(self, model): ...
    def submit(self, model): ...
    def status(self, run_id): ...
    def collect(self, run_id): ...
```

具体 Agent 的选择、模型、API endpoint、命令、权限和 session 生命周期由 host 提供，不属于 PaperSim 库。

推荐的外部 host profile：

```text
~/.config/papersim/host.json
```

示例字段：

```json
{
  "agent": {
    "adapter": "current_agent",
    "profile": "default"
  },
  "solvers": {
    "comsol": {
      "adapter": "comsol",
      "profile": "~/.config/papersim/yeesuan_comsol.json"
    }
  },
  "examples": {"yeesuan_comsol": "examples/mvp/yeesuan_comsol"}
}
```

`Engine.open()` 只负责接收已构造好的 adapter registry，或由 host 读取 profile 后注入：

```python
engine = Engine.open(
    "/path/to/PaperSimWorkspace",
    agents={"current": current_agent},
    solvers={"comsol": comsol_backend},
)
```

五个业务操作仍然是：

```text
case
model
run
compare
assess
```

库不读取 Agent 的模型名称、API key、session token 或平台账号。

### 7.3 每次启动必须经过 PaperSim 握手

Agent 每次开始 PaperSim 工作时，必须先完成运行时握手：

1. 从固定安装位置导入 `papersim`；
2. 输出 `papersim.__version__` 和 schema version；
3. 通过 host profile 加载 `AgentAdapter` 和 `SolverBackend`；
4. 调用 `Engine.open()`；
5. 验证 workspace schema 和外部 artifact reference；
6. 验证当前 Agent capability；
7. 握手失败则停止，不允许 Agent 自己修改库代码绕过。

每次 Case、Model、Run、Compare、Assess 的 `producer` 字段必须记录：

```text
papersim_version
schema_version
adapter_name
adapter_version
host_name
```

### 7.4 防止 Agent 随意修改 PaperSim

正常运行和开发必须分开：

```text
runtime mode
  库只读
  只能调用 Engine
  只能写 workspace
  adapter 只能通过 profile 注入

development mode
  允许修改库
  必须跑 contract tests
  必须 bump schema/version
  必须生成 migration
```

约束：

- Agent 的默认工作目录是 workspace，不是 `PaperSim/src`；
- Agent 不得通过直接 import 内部模块绕过 `Engine`；
- Agent 不得修改 installed `papersim` package；
- Agent 不得直接写 `objects/`、`artifacts/` 或 JSON canonical files；
- paper 原文只读；
- 只有 host 可以决定使用哪个 AgentAdapter；
- library 代码变更必须被识别为开发任务，不能混入论文复现任务。

## 8. Canonical store

file-first：

```text
PaperSim/
└── paper/original/              # canonical 原文仓库

PaperSimWorkspace/
├── objects/
│   ├── case_<case_id>.json
│   ├── model_<model_id>.json
│   ├── run_<run_id>.json
│   ├── compare_<compare_id>.json
│   └── assess_<assess_id>.json
├── artifacts/
│   ├── <sha256>.bin
│   └── model_<model_id>__bundle.tar.gz
└── tmp/
```

`objects/`、`artifacts/` 和 `tmp/` 内只放文件，不创建子目录。

`objects/case_<case_id>.json` 只保存对象引用和状态，不复制 Model、Run、Compare 或 Assess。模型 Markdown、solver bundle、日志和输出全部作为 artifact 文件保存，并由对象 JSON 通过 SHA-256 引用。

如果以后需要索引，可以增加可重建的 SQLite projection，但它不是 canonical state。

## 9. 求解器接口

Core 只认识：

```python
class SolverBackend(Protocol):
    def validate(self, model): ...
    def build(self, model): ...
    def submit(self, model): ...
    def status(self, run_id): ...
    def collect(self, run_id): ...
```

COMSOL 是第一个 adapter，不是 core domain。

COMSOL adapter 负责：

- `model.spec.json` 到 COMSOL API/physics 的翻译；
- Java 或 model file 生成；
- solver 版本和 compile log；
- 本地、SSH 或 Slurm 提交；
- 输出收集和验证；
- 无法翻译时返回 `UnsupportedModel` 或 `TranslationGap`。

### 9.1 Yeesuan COMSOL MVP 样例

Yeesuan COMSOL 连接方式只作为可删除、可替换的 MVP 样例维护；PaperSim 库不定义站点、网关、账号、实例、密钥或调度参数。

绝对位置：

```text
/path/to/PaperSim/examples/mvp/yeesuan_comsol/
├── README.md
├── adapter.py
├── yeesuan_executor.py
├── workflow.md
├── comsol_batch.sh
├── comsol_job.slurm
└── probe_remote.py
```


MVP 样例必须覆盖：

- gateway host、port、account、instance selection 和 host-key policy；
- 当前 CPU instance、remote user、environment script、COMSOL executable 和 version；
- password 只从 mode-0600 外部 secret file 读取；
- connection probe；
- durable remote case layout；
- input upload 和 SHA-256 验证；
- Slurm partition/resource discovery；
- `sbatch` submission；
- `squeue`、`sacct`、COMSOL batch log 和 artifact verification；
- download 与 hash 复核；
- 失败时 fail closed，不把 Slurm `COMPLETED` 单独当作成功。

凭据和连接配置不得进入 PaperSim 仓库：

```text
~/.config/papersim/yeesuan_password
~/.config/papersim/yeesuan_comsol.json
```

库只定义 `SolverBackend` 和 `RemoteExecutor` 接口；`ComsolBackend` 消费用户注入的 executor。Yeesuan 的 SSH/SCP、实例选择、Slurm 和本地配置全部位于 `examples/mvp/yeesuan_comsol/`，不进入库代码。

### 9.2 MVP 使用方式

第一个 MVP candidate 使用 `Kobayashi1993A`：

```text
paper/original/Kobayashi1993A__<title>.pdf
-> current_agent builds Model draft
-> engine.model writes Model
-> engine.run submits Yeesuan COMSOL suite
-> engine.compare evaluates figure and convergence metrics
-> engine.assess gives reliability verdict
```

COMSOL 运行必须通过用户注入的 external solver executor 连接；不得把 SSH/SCP 逻辑写入具体论文脚本。

### 9.3 COMSOL 连接定义与库解耦

COMSOL adapter 的代码位于：

```text
PaperSim/src/papersim/comsol.py
```

这里只实现通用 adapter code，包括连接协议、上传、提交、查询、收集和验证。

环境相关信息不写入库：

```text
~/.config/papersim/yeesuan_comsol.json
```

该 profile 定义：

- gateway host、port、account；
- instance selection 或 instance id；
- remote user、environment script；
- COMSOL executable、version；
- Slurm partition、resource request；
- remote case root。

密码只放在：

```text
~/.config/papersim/yeesuan_password
```

权限必须为 `0600`，不得进入 profile、仓库、日志或 Agent 上下文。

### 9.4 平台迁移时的替换边界

平台迁移只替换 host 层，不修改 Case/Model/Run/Compare/Assess 定义：

```text
Codex / Claude / MCP / web / CLI
        |
        v
Host adapter
        |
        v
PaperSim Engine + schemas
        |
        +--> AgentAdapter
        +--> SolverBackend
```

平台迁移时必须保持：

- `from papersim import Engine` 不变；
- 五个对象和 schema 不变；
- `AgentAdapter` 和 `SolverBackend` contract 不变；
- workspace 数据不重写；
- host profile 可以替换；
- COMSOL profile 和 secret file 继续留在外部；
- skill 可以随 host 重新安装，但环境配置不进入 skill。

如果新平台需要不同的 Agent 调用方式，只新增一个新的 `AgentAdapter` 实现，不能修改 core contract 来适配平台。

## 10. 明确不做的功能

以下内容不进入 PaperSim core：

- 文献搜索、候选筛选、推荐和偏好；
- BibTeX、引用网络和通用文献库；
- 主题、项目和通用知识图谱；
- 全篇阅读、翻译和通用摘要；
- HTML、看板、网页 UI 和 publication report；
- chat、session、job queue 和 Agent 编排框架；
- Co Scientist 或类似插件；
- 第三方 backend vendoring；
- 独立 `Finding`、`Challenge`、`Variant`、`Plan`、`Artifact` 对象；
- 复杂 workflow engine；
- COMSOL 专有对象进入 domain。

## 11. 从旧 PaperEngine 迁移

只优先迁移：

- source 和 evidence reference；
- Markdown 模型、公式和参数抽取；
- paper result 的数值/图表引用；
- `CaseSpec`、acceptance、run manifest 和仿真 workflow；
- COMSOL translation 和 remote execution；
- 旧 Kobayashi1993A 及后续论文 PDF 先迁入 `paper/original/`，case 只保存 `paper_ref`。

不迁移：

- 搜索、筛选、偏好、BibTeX；
- 主题、web、HTML、Codex session、job manager；
- vendored third-party；
- 通用 deep-read 和与模型复现无关的输出。

详细分类见 `../MIGRATION_INVENTORY.md`。

## 12. 验收标准

v1 只验收一条 golden paper 主链：

```text
Case
-> Model
-> Run
-> Compare
-> revised Model
-> Run
-> Assess
```

最低要求：

- `model.md` 可以持续扩充；
- 每次扩充产生不可变的 `Model.id`；
- 每个 run 都能定位到具体 `Model.id`；
- baseline 不会被 variant 覆盖；
- Compare 能区分 observed、simulated、error 和 mismatch；
- Assess 能给出明确 verdict、scope 和 unresolved questions；
- 同一 task 可以替换不同 `AgentAdapter`；
- core 测试可以使用 fake solver；
- COMSOL 只通过 adapter 和 `yeesuan-comsol` skill 接入；
- 当前 Agent 可以通过同一 `AgentAdapter` contract 参与 `Case/Model/Compare/Assess`；
- 所有论文原文只存在于 `paper/original/`；
- 五个对象的成果均可通过 schema、validator 和 contract tests 验证；
- 每个阶段都有明确门禁，校验失败不能进入下一阶段；
- 每次运行都记录 PaperSim version、schema version、host 和 adapter；
- Agent 选择和 COMSOL connection profile 均位于库外，平台迁移不需要改写 core。

## 13. 实施顺序

1. 建立扁平的 `paper/original/` 和 `index.json`，实现原文去重和 `paper_ref`。
2. 实现五个对象、统一 envelope、JSON Schema、validator 和 contract tests。
3. 实现扁平 file-first workspace，并让 Engine 成为唯一 canonical writer。
4. 实现 `model.md -> model.spec.json` 的 Model version。
5. 实现 fake solver 的 `run`。
6. 实现 `compare`。
7. 实现 `model(parent=...)` 和迭代链。
8. 实现 `assess`。
9. 将 Yeesuan 连接实现保留在 `examples/mvp/yeesuan_comsol/`，不纳入 PaperSim 库接口。
10. 在扁平的 `comsol.py` 中接入 COMSOL adapter，并让 current Agent 按 skill 完成 Kobayashi1993A MVP。
11. 接入 current Agent 作为第一个 `AgentAdapter`，并实现 host profile 加载和启动握手。
12. 最后处理 legacy importer 和数据迁移。
