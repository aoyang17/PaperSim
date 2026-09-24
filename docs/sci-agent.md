# PaperSim Sci-Agent 规划

- 状态：Draft
- 日期：2026-09-18
- 关联：[ADR-0001](adr/ADR-0001-case-model-run-compare-assess.md)
- 目标：判断 PaperSim 如何从“可验证的仿真资产层”演进为 EvoMaster 类科学智能体工具，并明确五块核心能力的实施起点。

## 1. 结论先行

PaperSim 有机会成为科学仿真领域的 EvoMaster 类智能体，但不应从“先做一个会聊天的 Planner”开始。

推荐起步顺序是：

```text
1. 先定义什么叫“变好了”              -> Fitness Contract
2. 再定义智能体允许怎么改模型          -> Model Revision API
3. 用 3-5 个 golden case 冻结成功标准  -> Mini Benchmark
4. 最后接入有预算的 Planner            -> Agent Runtime
5. 再做沙箱、调度、恢复和规模化执行     -> Tool / Sandbox Runtime
```

原因：

- 没有 fitness function，Planner 只能追求“看起来像”，不能优化科学可靠性。
- 没有 Model Revision API，Agent 只能直接改 canonical 文件，无法保证 lineage。
- 没有 benchmark，无法判断 Agent 是变强了还是只是在过拟合当前案例。
- 没有沙箱和执行运行时，自主迭代会带来安全、资源和可复现性风险。

PaperSim 的最合理定位不是“通用 Agent 框架”，而是：

> **科学仿真智能体的可信执行、验证和进化底座。**

```text
EvoMaster / 上层 Agent
        |
        v
PaperSim Sci-Agent Runtime
        |
        +-- Planner
        +-- Model Revision
        +-- Tool Runtime
        +-- Compare / Assess Fitness
        +-- Benchmark / Memory
        |
        v
Case -> Model -> Run -> Compare -> Assess
```

## 2. 当前基线

PaperSim 现在已经具备：

- `Case -> Model -> Run -> Compare -> Assess` 五原语；
- `Engine` 唯一 canonical writer；
- 不可变 `Model.id` 和 lineage；
- `AgentAdapter` / `SolverBackend` 协议；
- COMSOL 6.4 adapter；
- 全局 `comsol-modeling` skill；
- build-only 与 solve-only 分离；
- artifact hash、日志、MPH 和数据验证；
- Kobayashi 1993 的真实 COMSOL Fig. 7 案例；
- Compare 的 observed/simulated/error/mismatch/uncertainty；
- Assess 的 reliability verdict。

当前缺少的是：

- 自动任务分解；
- 可计算的目标函数；
- 安全模型变异；
- 多步闭环控制；
- 工具沙箱和资源调度；
- 跨 case 记忆；
- benchmark 和隐藏验收；
- 多智能体协作和冲突裁决。

## 3. 五块核心能力

### 3.1 Fitness Contract：定义“什么叫成功”

这是第一优先级。

目标不是把科学判断简化成一个标量分数，而是定义一组可审计的 fitness vector：

```text
FitnessVector
- required_pass_rate
- metric_errors
- uncertainty
- reproducibility
- compute_cost
- human_interventions
- invalid_actions
- acceptance_hash
```

需要回答：

- 哪些指标是硬约束，哪些只是偏好；
- 每个指标的阈值来自哪里；
- 允许哪些 mismatch；
- 什么情况下必须停止；
- 什么情况下必须请求人工审查。

建议在现有字段基础上增加：

- `Objective`
- `StopCondition`
- `FitnessPolicy`
- `FitnessVector`
- `StopReason`

初步接口草案：

```python
@dataclass(frozen=True)
class FitnessPolicy:
    required_metrics: tuple[str, ...]
    hard_thresholds: Mapping[str, float]
    soft_weights: Mapping[str, float]
    max_iterations: int
    max_compute_seconds: int
    max_human_interventions: int

@dataclass(frozen=True)
class FitnessVector:
    required_pass_rate: float
    metric_errors: Mapping[str, float]
    uncertainty: Mapping[str, float]
    reproducibility: float
    compute_seconds: float
    human_interventions: int
    invalid_actions: int
```

验收标准：

- 同一输入和同一 Run 产生确定性 fitness vector；
- Assess 必须返回 `stop_reason`；
- 未达到硬阈值时不能被判定为 supported；
- fitness policy 和评估结果可 hash、可追溯。

### 3.2 Model Revision API：定义“允许怎么改”

Agent 不能直接修改 canonical Model。

需要引入显式的 revision intent：

```text
RevisionIntent
- parent_model_id
- change_class
- target
- proposed_value
- reason
- expected_effect
- evidence
```

`change_class` 至少包括：

```text
parameter
constitutive
boundary
initial_condition
solver
mesh
discretization
output_metric
assumption
```

推荐流程：

```text
Agent 提出 RevisionIntent
-> Engine 校验变更类别和目标
-> Agent 生成新的 Model draft
-> Engine 重新验证 model.md / model.spec.json
-> 形成新的不可变 Model.id
-> Run 绑定新 Model.id
```

必须保证：

- 旧 Model 永不覆盖；
- 每个 revision 都有 `change_reason`；
- paper fact、extracted fact、inference、assumption 分开；
- 单位、量纲和引用必须验证；
- 任何自动参数拟合都必须单独标记；
- Agent 不能删除失败的 Run 或 Compare。

第一批可自动化的变更应限制为：

1. 参数值；
2. 参数边界；
3. 网格尺寸；
4. 时间步；
5. 求解器容差；
6. 输出时间；
7. 已声明的 assumption 显式切换。

暂不允许自动修改：

- 主控方程结构；
- 本构定律类型；
- 物理场数量；
- 边界条件的物理语义；
- 论文事实本身。

### 3.3 Tool / Sandbox Runtime：定义“怎么可靠执行”

这是智能体真正能动手的前提。

需要支持：

- 本地 Python；
- COMSOL Java 编译；
- COMSOL batch build；
- COMSOL batch solve/export；
- SSH / Slurm；
- 文件上传下载；
- artifact hash；
- 参数扫描；
- 日志采集；
- 失败分类和恢复；
- 资源预算和超时。

必须有沙箱边界：

```text
SandboxPolicy
- allowed_commands
- allowed_paths
- network_policy
- cpu_limit
- memory_limit
- wall_time_limit
- max_parallel_jobs
- artifact_size_limit
```

执行结果必须是 typed result，而不是自由文本：

```python
@dataclass(frozen=True)
class ToolResult:
    status: str
    exit_code: int | None
    logs_ref: str | None
    artifacts: tuple[ArtifactRef, ...]
    resource_usage: Mapping[str, Any]
    error_class: str | None
```

验收标准：

- 失败任务可分类、可重试、可恢复到检查点；
- 每个工具调用都有输入 hash、输出 hash 和资源记录；
- Agent 无法执行未授权的 shell、路径或网络操作；
- 任何 solver 失败都不能伪装成 successful run。

### 3.4 Planner / Agent Runtime：定义“怎么迭代”

Planner 不应先于 fitness 和 revision API 存在，否则它没有可靠的目标，也没有安全的动作空间。

推荐闭环：

```text
Case Goal
-> 读取 Model / Run / Compare
-> 读取 FitnessVector
-> 诊断 gap
-> 生成候选变更
-> 选择优先级最高且成本最低的动作
-> Model Revision
-> Run
-> Compare
-> Assess
-> 判断继续、升级审查或停止
```

Planner 的动作空间：

```text
run
compare
revise_parameter
revise_assumption
revise_numerics
request_new_data
request_human_review
stop
```

必须有的护栏：

- 最大迭代次数；
- 最大计算预算；
- 最大人工介入次数；
- 不允许伪造证据；
- 不允许覆盖旧 canonical 对象；
- 不允许跳过 Compare 直接 Assess；
- 不允许在缺少论文 observation 时给 supported。

第一版 Planner 应该是：

> **有预算、有动作白名单、每一步都可回滚、关键物理修改需人工批准。**

### 3.5 Mini Benchmark：定义“Agent 是否真的变强”

没有 benchmark，就没有智能体进化。

第一批 benchmark 不应一开始覆盖所有物理，而应覆盖能力阶梯：

| 等级 | Benchmark 类型 | 验证能力 |
|---|---|---|
| B0 | 参数已知的小模型 | 是否能复制 baseline |
| B1 | 参数未知但边界清楚 | 是否能做参数校准 |
| B2 | 论文缺 assumption | 是否能发现 gap |
| B3 | 有多个候选本构 | 是否能选择模型 |
| B4 | 有实验数据 | 是否能做仿真-实验闭环 |
| B5 | 多尺度交接 | 是否能管理跨尺度参数和不确定性 |

建议首个 benchmark：

```text
Kobayashi 1993 Fig. 7
```

不是因为它简单，而是因为已经具备：

- 论文；
- 方程；
- 参数；
- 多 case；
- COMSOL MPH；
- 数据；
- 图表；
- 12 项验收；
- 当前 verdict。

可以先把它拆成：

```text
B0：读取已有 Final Model，重复 Run 和 Compare
B1：只允许修改 delta
B2：允许修改网格和时间步
B3：允许修改 noise/R0 assumption
B4：要求识别 mismatch 并给出 unresolved questions
```

每个 benchmark 必须包含：

- 输入；
- 隐藏验收条件；
- 允许动作；
- 禁止动作；
- 计算预算；
- 成功条件；
- 失败分析；
- 期望最终 verdict。

## 4. 推荐起步顺序

### P0：Fitness + Revision Contract

先做最小闭环的契约，不先做复杂 Planner。

任务：

- 定义 `FitnessPolicy`、`FitnessVector`、`StopCondition`；
- 在 Compare/Assess 中输出机器可读 fitness；
- 定义 `RevisionIntent`；
- 实现 7 类低风险参数/数值 revision；
- 增加 contract tests。

产出：

- Agent 能知道“当前离成功还差什么”；
- Agent 能安全提出一个可验证的模型修改；
- Engine 仍然保持唯一 canonical writer。

### P0：Mini Benchmark v0

任务：

- 冻结 Kobayashi B0/B1；
- 明确允许动作和隐藏指标；
- 记录 baseline 人工路径；
- 建立 agent 评分脚本；
- 加入回归测试。

产出：

- 可以比较“人工 vs Agent”；
- 可以测量迭代次数、计算成本、成功率和人工介入率。

### P1：半自主 Planner

任务：

- 只允许 run、compare、低风险 revision；
- 每轮必须给出 action、reason、expected effect；
- 物理结构修改必须请求人工审查；
- 支持 stop、retry、budget-exhausted。

产出：

- 一个真实案例可以在有限预算内自动迭代；
- 最终仍必须由 Engine 生成 Compare 和 Assess。

### P1：Tool / Sandbox Runtime

任务：

- 工具注册表；
- 命令白名单；
- 本地/远程执行适配；
- 资源配额；
- 日志和 artifact 采集；
- 失败分类和恢复。

产出：

- Agent 不再直接操作 shell；
- 执行可复现、可审计、可中断。

### P2：Memory + Multi-Agent

任务：

- 跨 case 的失败模式记忆；
- 方程、单位、参数、边界模板检索；
- Reproduction Agent / Critic Agent / Assessor Agent 分离；
- 冲突裁决和版本合并。

产出：

- 多假设并行探索；
- 可积累的领域经验；
- 接近 EvoMaster 类的进化系统。

## 5. 里程碑

### M1：可信半自动循环

```text
已有 Model
-> Agent 提议低风险 revision
-> Engine 校验
-> Run
-> Compare
-> Assess
-> 继续或停止
```

成功标准：

- 至少一个真实案例；
- revision 不覆盖旧 Model；
- 所有动作有证据和 hash；
- 无未授权修改；
- 预算耗尽时能安全停止。

### M2：单 Case 自主迭代

成功标准：

- 在预设预算内自动完成至少两轮 revision；
- 每轮都有 fitness 改善或明确证伪；
- 最终 Assess 不由模型生成者单独决定。

### M3：多 Case Benchmark

成功标准：

- 至少 5 个 golden case；
- 有隐藏验收；
- 可以比较不同 Agent；
- 可以测量 success rate、cost、iterations、human intervention rate。

### M4：多尺度科学 Agent

成功标准：

- 能处理 DFT/MD -> 相场 -> 连续介质的参数交接；
- 能追踪不确定性和 assumption；
- 能根据实验数据更新模型可靠性判断；
- 能输出多尺度 verdict 而不是单点结果。

## 6. 关键指标

建议第一版只跟踪以下指标：

```text
acceptance_rate
iterations_to_acceptance
mean_compute_seconds
mean_human_interventions
reproducibility_rate
invalid_action_rate
false_supported_rate
unresolved_question_count
cost_per_accepted_model
```

其中最重要的是：

- `false_supported_rate`：不能把不可靠模型判成 supported；
- `reproducibility_rate`：换 Agent/环境后结果是否可以重现；
- `cost_per_accepted_model`：是否比人工更有效。

## 7. 明确不做

第一阶段不做：

- 通用 Agent 框架；
- 聊天式科研助手；
- 自动生成论文；
- 自动替代物理学家判断；
- 无限制修改本构方程；
- 无限制调用外部网络；
- 无 benchmark 的自我进化；
- 无人工审查的结构性物理修改。

## 8. 立即下一步

建议下一步直接做三个小交付：

1. `docs/sci-agent.md`：本规划文档；
2. `contracts.py`：增加 `FitnessPolicy`、`FitnessVector`、`StopCondition`、`RevisionIntent` 草案类型；
3. `tests`：为 fitness vector、revision immutability、stop condition 写 contract tests。

然后才接入第一个 Planner。

最终判断：

> PaperSim 可以先不做 EvoMaster 的“自主思考层”，但必须先把自己的 fitness、revision 和 execution 底座做成可靠的 Agent Runtime。底座稳定后，上层 Planner 和多 Agent 才有意义。
