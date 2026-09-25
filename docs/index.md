# PaperSim

PaperSim 将论文数值模型复现组织为不可变的 Case 迭代。每个阶段都有结构化输入、确定性检查和明确输出，只有通过前置门禁的模型才能进入下一阶段。

## 核心链路

```text
论文证据
  → IR
  → 人工批准
  → build-only Java
  → built MPH
  → 实现审计
  → solve-only 求解
  → 数值审计
  → 论文结果比较
  → assess / report
```

## PaperSim 解决的问题

PaperSim 不把“COMSOL 正常退出”当作复现成功。它分别回答：

1. 论文事实是否被正确提取并绑定到原文证据；
2. COMSOL 是否忠实实现了批准后的 IR；
3. 求解是否达到终点、保持守恒并满足离散敏感性要求；
4. 论文图表和趋势能否在声明条件下被独立复现；
5. 哪些结论依赖论文未报告的假设，因此只能得到 `qualified` 而不是 `supported`。

## MVP 案例

当前完整案例是：

```text
kobayashi1993_dendrite
```

案例覆盖 Eq. (3)-(5) 与 Fig. 7 的五组各向异性扫描：

```text
delta = 0, 0.005, 0.01, 0.02, 0.05
tfinal = 1.4
comparison times = 0.2, 0.8, 1.4
```

最终结果：

| 项目 | 结果 |
|---|---:|
| Case state | `assessed` |
| Verdict | `qualified` |
| Required acceptance | `12/12 PASS` |
| Numerical checks | `15/15 PASS` |
| Fig. 7 mean IoU | `0.328294` |
| Fig. 7 normalized Chamfer | `0.0262006` |

从案例总览开始阅读：

[Kobayashi 1993 完整 MVP](mvp/kobayashi1993/index.md){ .md-button .md-button--primary }
