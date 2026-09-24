# 给 Codex 的 PaperSim 实现 Prompt

下面这段可以直接交给 Codex。它假设你已有 Python 结构化抽取模块，Codex 只需要建立 IR、对接抽取输出、实现审计 A/B 和合并判定。

---

## 任务背景

PaperSim 是一个把论文本构方程参数复现到 COMSOL 的工具。现有代码中已经有一个 **Python 结构化抽取模块**（下面简称 `extractor`），它从 PDF 中抽取出参数、公式、边界条件、几何等结构化数据，但还没有统一的 IR，也没有审计机制。

你的任务是：**在现有 `extractor` 基础上，建立 PaperSim IR，实现审计 A（确定性验证）、审计 B（LLM 对抗性审查）、以及合并判定状态机。**

不要重写 `extractor`。通过适配层对接它的输出。

---

## 目录结构

请在项目根目录下创建以下结构：

```
papersim/
  ir/
    __init__.py
    schema.py          # IR 数据模型与 JSON Schema
    builder.py         # 从 extractor 输出构建 IR
    store.py           # IR 持久化、哈希、版本
    state.py           # 状态机定义
  audit_a/
    __init__.py
    evidence.py        # 证据锚点验证
    value_rebuild.py   # 参数值可重建性
    ast_compare.py     # 方程 AST 对比
    symbol_table.py    # 符号表完备性
    cross_source.py    # 多源交叉
    unit_dimension.py  # 单位与量纲
    runner.py          # 审计 A 总入口
  audit_b/
    __init__.py
    probes.py          # 完备性探针生成
    adversarial.py     # 对抗性审查
    coref.py           # 指代消解检查
    reextract.py       # 独立重抽取
    reverse_query.py   # 反向提问
    runner.py          # 审计 B 总入口
  merge/
    __init__.py
    decision.py        # 合并判定
    report.py          # 审计报告生成
  adapters/
    __init__.py
    extractor_adapter.py  # 对接现有 extractor
  cli.py               # 命令行入口
  config.py            # 配置
```

---

## 1. IR 数据模型（`papersim/ir/schema.py`）

用 Pydantic v2 定义 IR。**规范形式是 JSON，单一事实源。**

必须包含以下实体：

```python
from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum

class Status(str, Enum):
    EXTRACTED = "extracted"
    QUOTE_VERIFIED = "quote_verified"
    OFFSET_VERIFIED = "offset_verified"
    UNIT_CHECKED = "unit_checked"
    DIMENSION_CHECKED = "dimension_checked"
    CROSS_VERIFIED = "cross_verified"
    ADVERSARIAL_REVIEWED = "adversarial_reviewed"
    VERIFIED = "verified"
    IR_ERROR = "ir_error"
    IR_GAP = "ir_gap"
    PAPER_UNSPECIFIED = "paper_unspecified"
    PAPER_AMBIGUOUS = "paper_ambiguous"
    NEEDS_HUMAN = "needs_human"

class Evidence(BaseModel):
    source: str                    # 文件路径或 ID
    source_hash: str               # sha256 of source
    page: Optional[int]
    char_start: int
    char_end: int
    quote: str
    quote_hash: str                # sha256 of quote
    bbox: Optional[list[float]] = None

class Parameter(BaseModel):
    id: str
    symbol: str
    name: Optional[str]
    value: Optional[float]
    unit: Optional[str]
    expression: Optional[str] = None   # 如果是函数，存表达式
    evidence: Evidence
    status: Status = Status.EXTRACTED
    comsol_var: Optional[str] = None
    comsol_expression: Optional[str] = None
    audit_trail: list[str] = Field(default_factory=list)
    ambiguity: Optional[dict] = None
    inference_basis: Optional[str] = None  # 如果是 inferred，说明依据

class Equation(BaseModel):
    id: str
    latex: Optional[str]
    ast: dict                       # 抽象语法树
    symbols: list[str]
    evidence: Evidence
    status: Status = Status.EXTRACTED
    assumptions: list[str] = Field(default_factory=list)

class MaterialModel(BaseModel):
    id: str
    model_name: str                 # e.g., "neo_hookean"
    parameters: list[str]           # 引用 Parameter.id
    evidence: Evidence
    status: Status = Status.EXTRACTED
    assumptions: list[str] = Field(default_factory=list)

class BoundaryCondition(BaseModel):
    id: str
    kind: str
    target: Optional[str]
    value: Optional[str]
    evidence: Evidence
    status: Status = Status.EXTRACTED

class Geometry(BaseModel):
    id: str
    dimension: Optional[int]
    description: str
    evidence: Evidence
    status: Status = Status.EXTRACTED

class AuditEvent(BaseModel):
    timestamp: str
    actor: Literal["extractor", "audit_a", "audit_b", "merge", "human"]
    action: str
    entity_id: Optional[str]
    detail: dict
    prev_hash: Optional[str]
    event_hash: str

class IR(BaseModel):
    ir_version: str = "0.1"
    paper_id: str
    source_hash: str
    parameters: list[Parameter] = []
    equations: list[Equation] = []
    materials: list[MaterialModel] = []
    boundary_conditions: list[BoundaryCondition] = []
    geometry: list[Geometry] = []
    audit_log: list[AuditEvent] = []
    status: Status = Status.EXTRACTED
    ir_hash: Optional[str] = None
```

同时导出 JSON Schema，供 LLM 和验证器使用。

---

## 2. 适配层（`papersim/adapters/extractor_adapter.py`）

现有 `extractor` 输出的字段名可能与 IR 不一致。写一个适配器：

```python
def extractor_output_to_ir(extractor_output: dict, paper_id: str, source_hash: str) -> IR:
    """
    将现有 extractor 的结构化输出转换为 IR。
    要求：
    - 每个参数/方程/边界条件都必须有 evidence（char_start/end/quote）
    - 如果 extractor 没有输出 evidence，则标记为 ir_gap，并记录缺失原因
    - 计算每个 quote 的 hash
    - 调用 IRStore 计算 ir_hash
    """
```

**约束**：
- 不允许丢弃 extractor 的任何字段。如果 IR schema 里没有对应字段，放入 `extras` 或记录到 `audit_log`。
- 如果 extractor 输出的字段无法映射，抛出异常，不要静默忽略。

---

## 3. IR 构建（`papersim/ir/builder.py`）

```python
def build_ir(extractor_output: dict, pdf_path: str) -> IR:
    """
    1. 读取 PDF，计算 source_hash
    2. 调用 extractor_adapter 转换
    3. 为每个实体计算 evidence.quote_hash
    4. 初始化 audit_log，记录构建事件
    5. 计算 ir_hash
    6. 返回 IR
    """
```

---

## 4. IR 持久化（`papersim/ir/store.py`）

- 规范形式：`ir.json`（canonical JSON，键排序，无空格）
- 哈希：`ir_hash = sha256(canonical_json(ir))`
- 每次修改 IR，追加 `AuditEvent`，用哈希链串联
- 提供 `load_ir`, `save_ir`, `diff_ir`, `verify_ir_hash`

---

## 5. 状态机（`papersim/ir/state.py`）

定义合法状态转移：

```
extracted
  → quote_verified
  → offset_verified
  → unit_checked
  → dimension_checked
  → cross_verified
  → adversarial_reviewed
  → verified

任一环节失败：
  → ir_error（可自动修正）
  → ir_gap（可自动补全）
  → paper_unspecified（升级人类）
  → paper_ambiguous（升级人类）
```

每个状态转移必须记录 `AuditEvent`。

---

## 6. 审计 A（`papersim/audit_a/`）

审计 A 是**确定性验证**，不调用 LLM。每个验证器接收 IR 和原文，输出 `ValidationResult`：

```python
class ValidationResult(BaseModel):
    entity_id: str
    validator: str
    passed: bool
    reason: Optional[str]
    detail: dict
```

### 6.1 证据锚点验证（`evidence.py`）

对每个带 Evidence 的实体：

1. 从 PDF 取 `text[char_start:char_end]`
2. 检查 `text == evidence.quote`
3. 检查 `sha256(text) == evidence.quote_hash`
4. 检查 `sha256(pdf_bytes) == evidence.source_hash`

四项全通过 → `passed=True`。任一失败 → `ir_error`。

### 6.2 参数值可重建（`value_rebuild.py`）

对每个 Parameter：

1. 用正则 + 单位解析从 `evidence.quote` 中提取数字和单位
2. 换算到 IR 中声明的单位
3. 与 IR 的 `value` 比较，容差 `1e-6` 相对误差

如果 `evidence.quote` 中找不到数值 → `ir_gap`（可能原文用表格或图）。

### 6.3 方程 AST 对比（`ast_compare.py`）

对每个 Equation：

1. 从原文（LaTeX 或 OCR 文本）重建 AST
2. 与 IR 的 `ast` 做树编辑距离
3. 距离为 0 → 通过；否则 → `ir_error`

用 `sympy.parsing.latex.parse_latex` 或自定义解析器。

### 6.4 符号表完备性（`symbol_table.py`）

1. 收集所有 Equation.ast 中出现的符号
2. 每个符号必须在 IR 中有定义（Parameter 或局部变量）
3. 每个 Parameter 必须被至少一个 Equation 或 MaterialModel 引用
4. 缺失定义 → `ir_gap`；多余定义 → 标记可疑，记录 `audit_log`

### 6.5 多源交叉（`cross_source.py`）

对每个 Parameter：

1. 从正文、表格、图注、附录分别抽取候选值
2. 换算到同一单位
3. 全部一致 → 通过
4. 不一致 → 记录 `candidates`，标记 `paper_ambiguous` 或 `ir_error`

### 6.6 单位与量纲（`unit_dimension.py`）

用 `pint` 和 `sympy`：

1. 每个 Parameter 的单位可解析
2. 每个 Equation 两边量纲一致
3. 表格数值与正文单位可对齐

量纲不一致 → `ir_error`。

### 6.7 审计 A 总入口（`runner.py`）

```python
def run_audit_a(ir: IR, pdf_path: str) -> list[ValidationResult]:
    """
    依次运行所有验证器。
    对每个失败结果，更新对应实体的 status。
    返回所有结果。
    """
```

---

## 7. 审计 B（`papersim/audit_b/`）

审计 B 是 **LLM 对抗性审查**。LLM 只读原文，不读 IR（除了反向提问）。每个模块接收原文和 IR（用于生成探针），输出 `ReviewResult`：

```python
class ReviewResult(BaseModel):
    entity_id: Optional[str]
    probe: str
    verdict: Literal["EXPLICIT", "INFERRED", "UNSPECIFIED", "AMBIGUOUS"]
    explanation: str
    suggested_fix: Optional[str]
```

### 7.1 完备性探针（`probes.py`）

为每个实体生成探针问题。模板化：

**参数探针**：
- `{symbol} 是常数还是函数？如果是函数，依赖什么变量？`
- `{symbol} 的单位是否明确？`
- `{symbol} 是否依赖其他参数？`
- `{symbol} 的测量条件是什么？`

**方程探针**：
- `该方程是否假设不可压缩？`
- `该方程是否等温？`
- `应变定义是工程应变还是真实应变？`
- `适用小变形还是大变形？`

**边界条件探针**：
- `是二维还是三维？`
- `是否对称？`
- `载荷是位移控制还是力控制？`

**材料模型探针**：
- `具体是哪种本构模型？`
- `参数对应哪个版本？`
- `是否有补充材料修正？`

### 7.2 对抗性审查（`adversarial.py`）

```python
def adversarial_review(paper_text: str, probes: list[str], llm_client) -> list[ReviewResult]:
    """
    对每个 probe，让 LLM 只读论文，回答：
    - EXPLICIT: 原文明确说了
    - INFERRED: 原文隐含，需要推断（LLM 必须给出推断依据）
    - UNSPECIFIED: 原文完全没说
    - AMBIGUOUS: 原文有多种解读（LLM 必须列出候选）
    要求 LLM 输出 JSON，包含 quote 证据。
    """
```

Prompt 模板：

```
你是一个严格的审稿人。只读下面的论文，回答每个问题。
对每个问题，标记：
- EXPLICIT: 原文明确说了，并给出原文引用
- INFERRED: 原文隐含，需要推断，并给出推断依据
- UNSPECIFIED: 原文完全没说
- AMBIGUOUS: 原文有多种解读，并列出所有候选

不要猜测。如果你不确定，标记为 UNSPECIFIED 或 AMBIGUOUS。

论文：
{paper_text}

问题：
{probes}

输出 JSON 数组。
```

### 7.3 指代消解（`coref.py`）

专门检查原文中的指代和省略：

```python
def coref_check(paper_text: str, ir: IR, llm_client) -> list[ReviewResult]:
    """
    找出原文中所有指代词（this, it, the modulus, as reported in [23] 等），
    让 LLM 判断：
    - 指代对象是否在 IR 中有对应实体
    - 指代是否明确
    - 如果指向外部文献，标记为 UNSPECIFIED
    """
```

### 7.4 独立重抽取（`reextract.py`）

```python
def independent_reextract(paper_text: str, llm_client) -> IR:
    """
    用另一个 LLM 实例（不共享上下文）只读原文，独立生成一份 IR。
    注意：这里只生成 IR 的参数/方程部分，不要求完整。
    """
```

对比两份 IR：

- 相同 → 高置信度
- 不同 → 标记 `paper_ambiguous`
- IR_1 有 IR_2 没有 → 可能是幻觉或遗漏，标记 `needs_human`
- IR_2 有 IR_1 没有 → 同上

### 7.5 反向提问（`reverse_query.py`）

```python
def reverse_query(ir: IR, llm_client) -> list[ReviewResult]:
    """
    只读 IR，不读原文。
    让 LLM 回答：如果要在 COMSOL 里复现这个模型，还缺什么信息？
    LLM 列出的缺失项，就是 IR 完备性的直接证据。
    """
```

### 7.6 审计 B 总入口（`runner.py`）

```python
def run_audit_b(ir: IR, paper_text: str, llm_client) -> list[ReviewResult]:
    """
    依次运行所有审查模块。
    汇总结果，按 verdict 分类。
    """
```

---

## 8. 合并判定（`papersim/merge/decision.py`）

```python
def merge_decisions(
    ir: IR,
    audit_a_results: list[ValidationResult],
    audit_b_results: list[ReviewResult],
) -> IR:
    """
    对每个实体：
    1. 如果审计 A 有失败 → ir_error 或 ir_gap
    2. 如果审计 B 有 UNSPECIFIED → paper_unspecified
    3. 如果审计 B 有 AMBIGUOUS → paper_ambiguous
    4. 如果审计 B 有 INFERRED 但 IR 无 inference_basis → ir_gap
    5. 全部通过 → verified

    更新 IR 中每个实体的 status 和 audit_trail。
    生成合并报告。
    """
```

判定优先级：

```
ir_error > ir_gap > paper_ambiguous > paper_unspecified > verified
```

只有 `verified` 的实体才能进入代码生成。`ir_error` 和 `ir_gap` 触发自动修正队列。`paper_*` 触发人类升级。

---

## 9. 审计报告（`papersim/merge/report.py`）

生成结构化报告：

```json
{
  "paper_id": "...",
  "ir_hash": "...",
  "summary": {
    "verified": 12,
    "ir_error": 1,
    "ir_gap": 2,
    "paper_unspecified": 3,
    "paper_ambiguous": 1
  },
  "entities": [
    {
      "id": "param_E",
      "status": "verified",
      "audit_a": [...],
      "audit_b": [...],
      "audit_trail": [...]
    }
  ],
  "human_required": [
    {
      "entity_id": "param_alpha",
      "reason": "paper_ambiguous",
      "candidates": [...],
      "evidence": [...]
    }
  ]
}
```

同时生成人类可读的 Markdown 版本。

---

## 10. CLI 入口（`papersim/cli.py`）

```bash
# 构建 IR
python -m papersim.cli build-ir --paper paper.pdf --extractor-output extractor.json --out ir.json

# 运行审计 A
python -m papersim.cli audit-a --ir ir.json --paper paper.pdf --out audit_a.json

# 运行审计 B
python -m papersim.cli audit-b --ir ir.json --paper paper.pdf --out audit_b.json

# 合并判定
python -m papersim.cli merge --ir ir.json --audit-a audit_a.json --audit-b audit_b.json --out final_ir.json --report report.md

# 一键全流程
python -m papersim.cli run --paper paper.pdf --extractor-output extractor.json --out-dir output/
```

---

## 11. 实现约束

1. **不允许 LLM 直接写 IR 文件**。LLM 只输出 JSON，由 Python 验证后合并。
2. **不允许丢弃 extractor 的任何字段**。无法映射的字段记入 `audit_log` 或 `extras`。
3. **每个状态转移必须记录 AuditEvent**，哈希链串联。
4. **审计 A 不调用 LLM**。纯确定性。
5. **审计 B 的 LLM 必须能返回 JSON**，用函数调用或 JSON mode。
6. **所有验证器必须可单独测试**，有单元测试。
7. **IR 的 canonical JSON 必须可复现**：键排序，无空格，UTF-8。
8. **所有哈希用 sha256**，格式 `sha256:hexdigest`。
9. **异常不静默**：任何验证器抛异常，标记为 `ir_error`，记录堆栈。
10. **配置化**：LLM 模型、API key、容差、阈值都从 `config.py` 读取。

---

## 12. 测试要求

为每个模块写单元测试：

- `test_evidence_verifier.py`：正常、篡改、缺失
- `test_value_rebuild.py`：数值、单位换算、表格来源
- `test_ast_compare.py`：相同、多一项、少一项、符号替换
- `test_symbol_table.py`：完备、缺失、多余
- `test_cross_source.py`：一致、冲突、单一来源
- `test_unit_dimension.py`：正确、量纲不一致
- `test_probes.py`：探针生成覆盖所有实体类型
- `test_adversarial.py`：用 mock LLM 返回四种 verdict
- `test_merge_decision.py`：优先级、状态转移
- `test_store.py`：哈希、canonical JSON、版本

集成测试：用一篇小论文的 extractor 输出，跑完整流程，检查最终 IR 和报告。

---

## 13. 交付顺序

按以下顺序实现，每步可独立测试：

1. `ir/schema.py` + `ir/store.py`
2. `adapters/extractor_adapter.py` + `ir/builder.py`
3. `audit_a/evidence.py` + `value_rebuild.py`
4. `audit_a/ast_compare.py` + `symbol_table.py`
5. `audit_a/cross_source.py` + `unit_dimension.py`
6. `audit_a/runner.py`
7. `audit_b/probes.py` + `adversarial.py`
8. `audit_b/coref.py` + `reextract.py` + `reverse_query.py`
9. `audit_b/runner.py`
10. `merge/decision.py` + `report.py`
11. `cli.py`
12. 测试与文档

---

## 14. 关键设计原则（写在 README 顶部）

> - **IR 是单一事实源**。所有下游从 IR 生成，不直接手改。
> - **审计 A 负责“IR 有没有录错”**，确定性验证，不调用 LLM。
> - **审计 B 负责“原文有没有说清”**，LLM 对抗性审查。
> - **录错了 → 自动修正；原文没说 → 升级人类**。
> - **人类只看最终量化图表结果**，不看中间参数。
> - **无证据不生成，未验证不运行，有差异可追溯**。

---

请按以上结构实现，先建立 IR 和 store，再对接 extractor，然后实现审计 A，再实现审计 B，最后做合并判定和 CLI。每完成一个模块，运行单元测试。完成后输出一份 README，说明如何使用和扩展。