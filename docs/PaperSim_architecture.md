# PaperSim Architecture

## 1. 定位

PaperSim 是一个受约束、可追溯的论文仿真复现工具。它把论文中的模型事实转换为可审计的中间表示，再生成 COMSOL 模型，最后对模型实现、数值求解和论文结果进行闭环检查。

核心原则只有三条：

- **LLM 只负责理解和提出候选解释，不直接生成或运行 Java。**
- **Python、JSON 和规则负责结构化、验证、状态推进和报告。**
- **无证据不生成，未批准不运行，结果不一致时不直接归因。**

PaperSim 的目标不是证明论文作者是否造假，而是回答：

1. 论文模型和结果是否被正确提取；
2. COMSOL 是否忠实实现了批准的模型；
3. 求解结果是否数值可靠；
4. 论文报告结果能否在声明条件下被独立复现。

## 2. 总体架构

```text
论文 PDF / 补充材料
        │
        ▼
现有 Python 解析器
        │  ExtractionBundle
        ▼
候选 IR + 证据索引
        │
        ├── 确定性审计：证据、数值、单位、符号、方程、完备性
        └── LLM 审查：歧义、遗漏、未说明条件、独立解释
        │
        ▼
审计结果合并 + 人工批准
        │  approved IR / model.spec.json
        ▼
现有 COMSOL Java / MPH 建模 skills
        │
        ├── build：生成 Java，保存未求解 MPH
        ├── model audit：读回并核对 MPH
        └── solve：独立求解并保留日志、导出和诊断
        │
        ▼
Compare：论文观测与 COMSOL 可观测量比较
        │
        ▼
Assess：复现结论、置信度、差异原因和适用范围
```

架构保持现有五个核心原语：

```text
Case → Model → Run → Compare → Assess
```

审计不是一套平行业务流程，而是嵌入这些原语之间的门禁和证据记录。

## 3. 核心对象

### 3.1 Case

`Case` 定义一次论文复现任务，包含：

- 论文文件、补充材料和源文件哈希；
- 论文元数据和复现范围；
- 论文目标图表、表格或数值观测；
- 最低验收条件和期望输出。

### 3.2 IR

IR 是经过规范化的模型事实集合，也是后续生成和审计的事实来源。它至少覆盖：

- 参数、单位、表达式和证据；
- 符号表与变量作用域；
- 控制方程、本构关系、边界条件和初始条件；
- 几何、材料区域、网格、求解器和输出定义；
- 论文观测量及其提取、单位、归一化和容差；
- 假设、缺口、冲突和审计记录。

现有 `ExtractionBundle` 保留为解析器输出。IR 通过适配层无损接收它，不重写成熟的 PDF 方程和参数解析逻辑。

### 3.3 Audit Record

每个审计项都记录：

```text
entity_id
check_id
validator
passed / failed / unknown / not_applicable
evidence
reason
tool_version
```

审计结果必须绑定 IR 哈希和论文源文件哈希。

### 3.4 Model

`Model` 是由批准 IR 派生的可执行模型版本，包含 `model.md`、`model.spec.json`、Java 源码、模板版本和生成哈希。

模型版本不可覆盖。任何参数、方程、边界或求解设置变更都产生新的 Model 版本。

### 3.5 Run

`Run` 保存一次独立的构建或求解执行，包括：

- 求解器和版本；
- 环境信息；
- 构建/提交/求解状态；
- 日志、MPH、导出文件和诊断结果；
- 运行时使用的 Model 哈希。

Build 和 Solve 分离：Build 只保存未求解 MPH，Solve 由独立作业执行。

### 3.6 Compare

`Compare` 只比较明确声明的论文观测量和 COMSOL 可观测量。每个比较项必须有：

```text
paper_observable
comsol_expression
postprocess
unit / normalization
time or parameter condition
tolerance
paper value
simulated value
uncertainty
```

图中曲线或数值首先被视为 `reported_observation`，不是无条件的真实值。

### 3.7 Assess

`Assess` 汇总证据并给出有限范围内的判断，不直接宣称论文造假。最小结论集合为：

```text
reproduced
partially_reproduced
not_reproduced
underdetermined
```

如果差异仍无法归因，必须明确写出“当前证据不足”，而不是强行判定论文或模型错误。

## 4. 审计分层

### 4.1 IR 审计：我们是否正确理解论文

由 Python 确定性验证器完成，必要时由 LLM 提出审查问题：

- 证据文件、页码、bbox、引用和哈希是否有效；
- 参数值能否从证据重建，单位能否换算；
- 方程符号是否有定义，控制方程和本构关系是否分开；
- 方程量纲是否一致；
- 参数、边界、初值和输出是否存在未解释缺口；
- 正文、表格、公式、图注和补充材料是否冲突。

LLM 的输出只能形成候选问题或候选解释，必须经过 Python 校验，并在需要时人工批准。

### 4.2 COMSOL 实现审计：我们是否正确实现批准 IR

在求解前读回或导出模型快照，核对：

- 参数和单位；
- 变量表达式；
- 方程与本构关系；
- 物理接口、边界选择和初始值；
- 几何、材料、网格和求解器；
- 时间列表、参数扫描和导出表达式。

至少需要区分三种差异：

```text
IR ≠ Java
Java ≠ MPH
MPH ≠ 实际求解日志/导出
```

实现审计失败时，不能把结果差异归因于论文。

### 4.3 数值审计：求解结果是否可靠

最小检查集合为：

- 求解是否正常完成；
- 是否达到请求的时间或参数终点；
- 残差和收敛状态是否满足设定；
- 关键守恒量是否满足误差阈值；
- 场变量是否越界或违反本构适用范围；
- 至少一次网格或时间步敏感性检查；
- 导出量是否来自正确表达式和正确采样条件。

COMSOL “正常退出”本身不构成数值通过。

### 4.4 结果差异审计：论文与模型谁更可能有问题

只有 IR 审计、实现审计和数值审计都通过后，才进入差异归因。最小诊断顺序为：

1. 检查论文观测量与 COMSOL 输出量是否严格对应；
2. 检查单位、归一化、时间点、取值位置和后处理；
3. 检查论文内部正文、表格和图是否一致；
4. 进行一次只改变一个因素的诊断运行；
5. 根据证据更新多个解释的支持度。

最小解释类别为：

```text
observation_or_mapping_error
implementation_error
numerical_error
paper_omitted_condition
paper_inconsistency
underdetermined
```

PaperSim 记录“支持度”或“置信度”，不把它称为“造假概率”。造假判断超出仿真工具的证据范围。

## 5. 最小闭环工作流

### 阶段 A：建立 Case

登记论文、源文件哈希、复现范围、目标观测和最低验收条件。

### 阶段 B：解析并建立候选 IR

调用现有 Python 解析器。保留原始 `ExtractionBundle`，通过适配器生成候选 IR。LLM 只用于解释复杂文本、提出补充候选和指出歧义。

### 阶段 C：审计与批准

运行确定性审计，运行可选的 LLM 对抗审查，合并结果。存在失败、未知、缺口或歧义时不得自动生成可运行模型。人工只需要处理阻塞项，并批准一个带哈希的 IR 版本。

### 阶段 D：生成并审计 COMSOL 模型

从批准 IR 生成或录入 `model.spec.json` 和 Java。Build 作业保存未求解 MPH。随后执行模型快照审计；快照与批准规格一致才允许进入 Solve。

### 阶段 E：求解并审计数值

独立 Solve 作业运行 COMSOL，保留日志、MPH、导出和环境信息。运行数值审计，未通过时标记为数值不可靠，不进入论文归因。

### 阶段 F：比较与诊断

将论文观测和 COMSOL 可观测量按显式映射比较。若不一致，先记录差异，再执行有限数量的单因素诊断运行，不修改基线模型。

### 阶段 G：Assess 与报告

报告分别给出：

- 论文证据可信度；
- COMSOL 实现可信度；
- 数值结果可信度；
- 论文主张在声明条件下的一致性；
- 差异的当前最佳解释及其置信度；
- 尚未解决的问题和结论适用范围。

## 6. 状态与门禁

最小状态如下：

```text
extracted
  → audited
  → approved
  → model_generated
  → implementation_verified
  → solved
  → compared
  → assessed
```

阻塞状态为：

```text
needs_review
ir_error
ir_gap
paper_ambiguous
paper_unspecified
implementation_error
numerical_error
underdetermined
```

门禁规则：

- `audited` 不是 `approved`；机器审计通过仍需批准或明确批准策略；
- 只有 `approved` IR 才能生成正式 Java；
- 只有 `implementation_verified` 才能求解；
- 只有数值审计通过的 Run 才能支持论文结果归因；
- 所有对象通过 ID、哈希和父对象引用形成不可覆盖的证据链。

## 7. 责任边界

| 部件 | 负责 | 不负责 |
|---|---|---|
| LLM | 理解文本、提出候选结构和问题 | 直接批准事实、写入最终 IR、运行 Java |
| Python | 解析适配、验证、状态机、比较、报告 | 替代物理判断和人工裁决 |
| JSON/IR | 保存规范事实、证据和版本 | 自动证明论文结论正确 |
| COMSOL skills/Java | 按批准规格建模和导出 | 自行改变论文假设 |
| 人工 | 处理歧义、批准假设、解释最终证据 | 用“看起来相似”替代量化审计 |

## 8. 最小可靠性定义

一次论文复现只有在以下条件同时满足时，才可称为“在声明条件下复现”：

1. 关键事实有可验证证据；
2. IR 已批准且未被修改；
3. Java/MPH 通过实现审计；
4. 求解通过最小数值审计；
5. 论文观测量与 COMSOL 输出量映射明确；
6. 结果在预先声明的误差和不确定度内；
7. 全部输入、运行、差异和结论可回放。

否则只能使用“部分复现”“未复现”或“证据不足”等更窄的结论。
