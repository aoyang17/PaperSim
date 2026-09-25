# 求解与审计

这一阶段回答：**数值结果是否可靠，并且能否支持论文 Fig. 7 的结论？**

## 1. 参数扫描

正式 solve-only 作业执行一个 Study，其中包含单次 Parametric Sweep：

```text
delta = 0, 0.005, 0.01, 0.02, 0.05
```

求解完成后，solved MPH 内保存：

```text
sol2/su1  delta=0
sol2/su2  delta=0.005
sol2/su3  delta=0.01
sol2/su4  delta=0.02
sol2/su5  delta=0.05
```

求解作业：

```text
job_id = 82149
state = COMPLETED
exit_code = 0:0
elapsed = 02:36:54
```

## 2. 一个重要的门禁失败

第一次导出只产生了 `delta=0.05`，因为 numerical 和 Data export 默认引用了单一 solution，而不是参数解数据集。

PaperSim 没有把这个结果直接算作通过，而是：

1. 检查 solved MPH 内部解决方案；
2. 确认五组参数解都存在；
3. 将导出绑定到 `dset2 / Parametric Solutions 1`；
4. 执行 export-only 作业，不重新求解。

修复后的导出包含：

| Artifact | 内容 |
|---|---|
| `iter001_global_all.csv` | 五组 delta 的完整时间历史 |
| `iter001_fields_all.csv` | 五组 delta 在 `t=0.2, 0.8, 1.4` 的 p/T 场 |

实际数据：

- [`iter001_global_all.csv`](https://github.com/aoyang17/PaperSim/blob/main/docs/mvp/kobayashi1993/assets/data/iter001_global_all.csv)
- [`metrics.json`](https://github.com/aoyang17/PaperSim/blob/main/docs/mvp/kobayashi1993/assets/data/metrics.json)
- [`job_status.json`](https://github.com/aoyang17/PaperSim/blob/main/docs/mvp/kobayashi1993/assets/data/job_status.json)
- [`remote_hashes.json`](https://github.com/aoyang17/PaperSim/blob/main/docs/mvp/kobayashi1993/assets/data/remote_hashes.json)

## 3. 独立敏感性工况

仅有参数扫描不足以证明数值可靠，因此额外执行：

| Case | 变化 | Job ID | Elapsed |
|---|---|---:|---:|
| `control_delta020` | 关闭噪声的基线 | 83779 | 00:13:28 |
| `mesh_fine` | `hmesh=0.02` | 83780 | 00:27:26 |
| `timestep_fine` | `maxStep=0.0001` | 83781 | 00:21:56 |
| `seed_small` | `R0=0.12` | 83782 | 00:13:04 |
| `seed_large` | `R0=0.18` | 83783 | 00:11:28 |

敏感性比较使用 `t=0.8`，与论文 Fig. 7 的中间对比时刻一致。

## 4. 验收指标

| Metric | Actual | Rule | Result |
|---|---:|---:|---|
| `quality.p_min` | `-3.644014e-6` | `>= -0.05` | PASS |
| `quality.p_max` | `1.000001797` | `<= 1.05` | PASS |
| `quality.max_relative_enthalpy_drift` | `1.96206e-13` | `<= 0.01` | PASS |
| `convergence.mesh_tip_relative_difference` | `0.00353607` | `<= 0.05` | PASS |
| `convergence.timestep_tip_relative_difference` | `0.0` | `<= 0.05` | PASS |
| `convergence.seed_tip_relative_range` | `0.00211416` | `<= 0.15` | PASS |
| `paper_trend.delta050_to_delta000_tip_ratio` | `1.85093` | `> 1.02` | PASS |
| `paper_trend.delta050_vertical_to_horizontal_extent_ratio` | `2.01351` | `> 1.10` | PASS |
| `paper_figure.fig7_mean_iou` | `0.328294` | `>= 0.25` | PASS |
| `paper_figure.fig7_normalized_chamfer` | `0.0262006` | `<= 0.10` | PASS |

基础检查也全部通过：

```text
solver_completed
requested_endpoint
log_errors
```

## 5. Fig. 7 定量比较

![Fig. 7 paper vs COMSOL](assets/fig7/fig7_paper_vs_comsol.png)

比较方法：

1. 将论文 Fig. 7 的每个 panel 数字化为二值 mask；
2. 从 COMSOL fields 中提取 `p >= 0.5` mask；
3. 统一到 `192 x 192` 网格；
4. 计算 IoU 和边界点 normalized Chamfer 距离；
5. 对 15 个 panel 取平均。

该项不是逐像素要求论文和数值结果完全相同，而是验证整体形貌和轮廓趋势具有可量化重叠。

## 6. 最终 verdict

PaperSim 的 assess 逻辑得到：

```text
state = assessed
verdict = qualified
confidence = high
failed_checks = []
```

为什么不是 `supported`：

```text
论文未报告 random seed
论文未报告 nucleation seed radius
```

因此结论是：

> 在 `noiseSeed=1993`、`R0=0.15` 以及声明的数值设置下，Eq. (3)-(5) 和 Fig. 7 的五组趋势及轮廓指标通过验收。

这比无条件声称“论文完全复现”更准确。
