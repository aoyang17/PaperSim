# PaperSim Implementation Plan

## 1. 目标

本计划实现一个**最小但可靠的论文复现与审计闭环**，优先保护现有成熟能力：

- 不重写现有 PDF 方程、参数和本构抽取脚本；
- 不重写现有 COMSOL Java/MPH 建模 skills；
- 不先开发复杂的人审 UI、完整知识图谱或大规模多 Agent 平台；
- 先让一个真实论文案例完成“解析 → 审计 → 批准 → 建模 → 求解 → 比较 → 结论”。

## 2. 范围控制

### 本阶段必须实现

- 候选 IR 与现有 `ExtractionBundle` 的无损适配；
- 证据、单位、方程、符号和缺口的最小确定性审计；
- 审计结果和人工批准的不可变记录；
- Java 生成门禁和 Run 门禁；
- COMSOL 模型快照或等价读回检查；
- 求解终点、残差、守恒、场值和基本收敛检查；
- 论文观测量与 COMSOL 输出量的显式映射；
- 差异报告、三个核心置信度和有限的单因素诊断；
- JSON 与 HTML 审计报告。

### 本阶段明确不做

- 不判断作者主观“造假概率”；
- 不自动修改论文模型并把修改结果称为复现；
- 不把参数拟合结果当作独立复现；
- 不支持任意 PDF 类型的全自动通用解析；
- 不建设复杂 Web 界面；
- 不把所有可能的物理、统计和因果分析一次性加入核心流程。

## 3. 目标交付链

```text
existing extractor
  → candidate IR
  → deterministic audit
  → human approval
  → approved model.spec.json
  → Java / unsolved MPH
  → COMSOL implementation audit
  → solve / diagnostics
  → observable comparison
  → discrepancy assessment
  → HTML report
```

## 4. 实施阶段

### P0：冻结最小契约

**目的：** 在写代码前明确唯一事实源、对象关系和状态门禁。

**工作项：**

- 定义 IR 的最小 JSON 结构；
- 定义证据引用、审计结果、批准记录和哈希格式；
- 定义论文观测量与 COMSOL 输出量的映射结构；
- 定义 `reproduction`、`calibration`、`sensitivity` 三种运行模式，首期只强制支持 `reproduction`；
- 明确 `model.spec.json` 与 IR 的派生关系；
- 为现有字段无法映射的内容保留 `extras` 或审计警告。

**验收：** 一份现有抽取 bundle 可以无损转换为规范 JSON，并能稳定生成相同哈希。

### P1：建立 IR 适配和最小审计

**目的：** 让“无证据、错单位、缺符号”在生成前失败。

**工作项：**

- 增加 ExtractionBundle → IR 的适配层；
- 复用现有 PDF 哈希、quote、bbox 和单位验证逻辑；
- 增加参数值重建和单位换算检查；
- 增加方程引用符号与变量定义检查；
- 增加控制方程、本构、边界、初值的完备性检查；
- 统一输出 `pass / fail / unknown / not_applicable`；
- 生成审计 JSON 和人类可读摘要。

**验收：** 篡改 PDF、证据引用、单位或符号时，审计失败且不会生成正式模型。

### P2：批准状态和生成门禁

**目的：** 防止绕过审计直接生成或运行模型。

**工作项：**

- 实现 IR 版本和批准记录；
- 批准记录绑定论文哈希、IR 哈希、审计结果哈希和规则版本；
- 修改 IR 后使旧批准自动失效；
- 在 Java 生成入口校验批准凭证，而不是只依赖 CLI 调用顺序；
- 在 Engine 的 Run 入口校验 Model 的当前状态、批准凭证和父对象关系；
- 保留每次修订、拒绝和人工决策的理由。

**验收：** 未批准、已修改、来源文件变化或审计结果过期时，生成和运行均被阻止。

### P3：COMSOL 实现闭环

**目的：** 证明 COMSOL 实际模型等于批准规格。

**工作项：**

- 明确 build-only Java 与 solve-only 作业的产物契约；
- 在 Java/MPH 产物中写入 IR、Model 和 Java 哈希；
- 增加 COMSOL 模型快照或读回导出；
- 核对参数、变量、方程、物理特征、选择集、初值、网格、求解器和输出；
- 将差异分成 `IR-Java`、`Java-MPH`、`MPH-Run` 三类；
- 将快照和核对结果写入 Run artifact。

**验收：** 故意修改 Java、选择集、参数或 solver 设置时，实现审计失败；未通过时不能进入正式求解。

### P4：数值可靠性和比较

**目的：** 防止“COMSOL 正常退出”被误认为复现成功。

**工作项：**

- 记录实际终点、残差和求解状态；
- 增加质量/能量/动量等与案例相关的最小守恒检查；
- 增加关键场变量边界和本构适用范围检查；
- 增加一次网格或时间步敏感性检查；
- 定义论文观测量、COMSOL 表达式、后处理、单位、归一化、采样条件和容差；
- 复用 Compare 生成量化误差和不确定度；
- 将图像数字化误差与数值误差分开记录。

**验收：** 求解未到终点、守恒失败、场值越界或观测量映射不明确时，不能给出“复现”结论。

### P5：最小差异诊断与报告

**目的：** 在结果不一致时，区分模型错误、数值错误、论文遗漏和证据不足。

**工作项：**

- 在 Compare 后生成结构化差异记录；
- 按固定顺序检查观测映射、单位、归一化、时间点和论文内部一致性；
- 支持有限的单因素诊断运行，每个变体继承基线且只改一个因素；
- 计算并记录：
  - 论文证据可信度；
  - COMSOL 实现可信度；
  - 数值结果可信度；
- 输出 `reproduced`、`partially_reproduced`、`not_reproduced`、`underdetermined`；
- 明确记录支持的解释，不输出“造假概率”。

**验收：** 对一个已知不一致案例，报告能够说明“当前模型是否可信、论文结果是否在声明条件下复现、仍有哪些未决解释”。

### P6：基准案例和回归测试

**目的：** 证明审计机制本身不会随功能迭代退化。

**工作项：**

- 选择至少一个已有真实 COMSOL 案例作为端到端基准；
- 为证据篡改、单位错误、符号缺失、批准伪造、Java 修改、MPH 修改和错误输出映射增加红队测试；
- 保存通过和失败案例的规范 JSON artifact；
- 对 IR 哈希、状态转移、门禁、快照比较和报告输出做回归测试；
- 记录解析成本、人工审批时间和端到端误差。

**验收：** 基准案例可重复完成闭环，红队输入均在正确阶段失败，既有抽取和 COMSOL 流程保持兼容。

## 5. 推荐开发顺序

```text
P0 契约
  ↓
P1 IR + 审计
  ↓
P2 批准与门禁
  ↓
P3 COMSOL 实现审计
  ↓
P4 数值审计 + Compare
  ↓
P5 差异诊断 + 报告
  ↓
P6 基准与回归
```

P0–P2 是第一条可运行闭环，完成后即可防止未经审计的模型进入 COMSOL。P3–P5 是第一个可靠复现闭环的必要部分，完成后才能区分“我们的模型不对”和“论文结果未能由声明条件推出”。

## 6. 每阶段的完成定义

每个阶段必须同时具备：

- 可持久化的 JSON 契约；
- 可重复执行的 Python 检查；
- 明确的失败状态；
- 单元测试和至少一个失败样例；
- 不覆盖历史 artifact；
- 可在最终 HTML 报告中追溯。

不以“代码可以运行”作为完成标准。完成标准是：失败可阻止、成功可解释、结果可回放。

## 7. 交付后的扩展方向

最小闭环稳定后，再按实际案例需求增补：

- 多来源证据图和更强的 AST/数学等价检查；
- 人审界面和批量批准；
- 更丰富的反事实诊断和参数敏感性分析；
- 多求解器后端；
- 金标准论文集和跨案例指标；
- 原始数据、实验记录与外部复现结果的联合审计。

这些功能都必须复用本计划建立的 IR、哈希、审计记录和门禁，不另建一套并行事实源。


## Implementation status

The canonical case-directory workflow is implemented in `case_contracts.py`, `case_store.py`, `case_audit.py`, `case_java.py`, `case_mph.py`, `case_implementation.py`, `case_numeric.py`, `case_report.py`, `case_workflow.py`, and `case_migration.py`. The default offline test gate is `pytest -m "not pdf and not comsol"`; real PDF and COMSOL integration use the `pdf` and `comsol` markers. The Kobayashi iter001 build and MPH readback are validated; numerical acceptance is complete only after the separate solve/export job and its metrics pass `case_numeric.py`.
