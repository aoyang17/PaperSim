# 完整复现步骤

这一页给出从空 workspace 到最终审计报告的标准流程。真实集群配置放在用户自己的外部 executor 中，不写入 PaperSim 库或本仓库。

## 0. 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[pdf,extraction,test,remote]'
```

## 1. 建立 Case

```bash
papersim --workspace /path/to/PaperSimWorkspace case init \
  --surname Kobayashi \
  --year 1993 \
  --topic dendrite \
  --paper /path/to/kobayashi1993_dendrite_paper.pdf \
  --title "Modeling and numerical simulations of dendritic crystal growth" \
  --goal "Reproduce Eqs. (3)-(5) and Fig. 7"
```

## 2. 创建迭代

```bash
papersim --workspace /path/to/PaperSimWorkspace iteration \
  kobayashi1993_dendrite --iteration 1
```

## 3. 提取并审计 IR

```bash
papersim --workspace /path/to/PaperSimWorkspace extract \
  kobayashi1993_dendrite --iteration 1 \
  --profile profiles/kobayashi1993_dendrite.json
```

提取会校验 PDF 哈希、页码、bbox、quote、单位、符号闭包和验收规则。未通过时不会写正式 IR。

## 4. 人工批准

```bash
papersim --workspace /path/to/PaperSimWorkspace approve \
  kobayashi1993_dendrite --iteration 1 \
  --approved-by "human:reviewer" \
  --reason "Evidence and assumptions reviewed"
```

## 5. 生成 build/solve Java

```bash
papersim --workspace /path/to/PaperSimWorkspace build \
  kobayashi1993_dendrite --iteration 1
```

此命令只生成：

```text
iter001_build.java
iter001_solve.java
```

## 6. 运行 build-only 作业

在外部 COMSOL 环境编译并执行 build Java。作业只允许保存：

```text
iter001_built.mph
```

记录 build：

```bash
papersim --workspace /path/to/PaperSimWorkspace build \
  kobayashi1993_dendrite --iteration 1 \
  --mph /path/to/iter001_built.mph \
  --status complete --exit-code 0 \
  --log-file /path/to/build.log
```

## 7. MPH 读回和实现审计

```bash
papersim --workspace /path/to/PaperSimWorkspace audit-implementation \
  kobayashi1993_dendrite --iteration 1 --from-mph
```

通过后，状态进入 `implementation_audited`。

## 8. 外部 solve-only 作业

真实 solve 通过用户注入的 external solver 执行：

```python
from adapter import build_backend
from papersim import Engine

solver = build_backend(
    config="/path/to/local/solver-config.json",
    password_file=None,
    suite="full",
)

engine = Engine.open(
    "/path/to/PaperSimWorkspace",
    solvers={"comsol": solver},
)
```

本案例使用的可替换样例位于仓库的 `examples/mvp/yeesuan_comsol/` 目录，接口说明见
[外部 Solver 接口](../../reference/external-solver.md)。

## 9. 导出全部参数解

必须将 numerical 和 Data export 绑定到参数解 dataset，而不是默认单一 solution。Kobayashi 模板使用：

```java
model.result().numerical("gev1").set("data", "dset2");
model.result().export("data1").set("data", "dset2");
```

导出：

```text
iter001_global_all.csv
iter001_fields_all.csv
```

## 10. 运行数值审计

```bash
papersim --workspace /path/to/PaperSimWorkspace audit-numeric \
  kobayashi1993_dendrite --iteration 1 \
  --raw-csv /path/to/iter001_global_all.csv \
  --metrics-json @/path/to/metrics.json
```

这里的关键不是“求解成功”，而是检查终点、守恒、边界、收敛、趋势和 Fig. 7 指标。

## 11. 评估和离线报告

```bash
papersim --workspace /path/to/PaperSimWorkspace assess \
  kobayashi1993_dendrite --iteration 1

papersim --workspace /path/to/PaperSimWorkspace report \
  kobayashi1993_dendrite --iteration 1
```

最终报告：

```text
report.html
```

报告完全离线，不依赖 CDN、MathJax 或外部 JavaScript。
