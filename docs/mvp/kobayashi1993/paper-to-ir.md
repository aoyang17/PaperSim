# Paper 到 IR

这一阶段回答：**我们是否真正正确理解了论文，并且每一项模型事实都能回到原文证据？**

## 1. Case 身份

```text
case_id = kobayashi1993_dendrite
paper = kobayashi1993_dendrite_paper.pdf
topic = dendrite
year = 1993
```

Case ID 由第一作者姓氏、年份和单个小写主题词生成，不能是任意路径片段。论文和 profile 的哈希会被写入 IR 和批准记录。

## 2. 方程与分类

| 方程 | 分类 | 数学形式 | COMSOL 映射 |
|---|---|---|---|
| Eq. (3) | control | `tau*p_t = div(Gamma) + p(1-p)(p-1/2+m(T))` | General Form PDE `gp` |
| Eq. (4a) | constitutive | `m(T)=alpha/pi*atan(gamma*(Teq-T))` | Variables `mT` |
| Eq. (4b) | constitutive | `epsilon=epsbar*(1+delta*cos(jmode*(theta-theta0)))` | Variables `epsilon`, `epsilonTheta` |
| Eq. (5) | control | `T_t = D*lap(T) + Klatent*p_t` | General Form PDE `gT` |

PaperSim 要求控制方程和本构关系分开：

- 控制方程在 PDE/ODE；
- 本构关系和辅助关系在 named Variables；
- PDE 通过 named Variables 引用本构量；
- 每个 Variable 必须有 Description 和单位。

## 3. 参数与假设

论文固定参数：

```text
epsbar = 0.01
tau = 0.0003
alpha = 0.9
gamma = 10
Klatent = 2
jmode = 4
theta0 = 0
D = 1
```

数值设置：

```text
L = 9
hmesh = 0.03
maxStep = 0.0002
delta = 0, 0.005, 0.01, 0.02, 0.05
tfinal = 1.4
comparison times = 0.2, 0.8, 1.4
```

论文未报告的补全：

| 参数 | 采用值 | 原因 |
|---|---:|---|
| `noiseSeed` | `1993` | 论文未给出随机种子 |
| `R0` | `0.15` | 论文未给出形核半径 |

这两个值不是从论文中“猜出来”的，而是显式 assumption。正因为存在它们，最终 verdict 是 `qualified`，不是 `supported`。

## 4. IR 审计

IR 提取会检查：

- 原文页码、bbox、quote 和哈希；
- 参数值能否从证据重建；
- 单位和量纲是否一致；
- 符号表是否闭合；
- 边界和初值引用是否存在；
- 每条验收指标是否有来源和计算条件。

读取实际 IR：

[`iter001_ir.json`](https://github.com/aoyang17/PaperSim/blob/main/docs/mvp/kobayashi1993/assets/data/iter001_ir.json)

## 5. 批准门禁

批准记录绑定：

```text
paper_sha256
profile_sha256
ir_sha256
IR audit hash
rule version
```

任何一项变化都会使旧批准失效。后续 Java 生成、build 记录和 solve 都要求当前批准仍然有效。

核心原则：

> 无证据不进入 IR，未审计不批准，未批准不构建。
