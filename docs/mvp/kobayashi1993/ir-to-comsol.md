# IR 到 COMSOL

这一阶段回答：**批准后的模型规格是否被 COMSOL 真实、完整地实现？**

## 1. 生成物

PaperSim 分离两类 Java：

```text
iter001_build.java
    生成模型、设置物理和网格、保存未求解 MPH

iter001_solve.java
    加载 built MPH、执行 Study、导出结果、保存 solved MPH
```

build-only 代码不能调用 `runAll()`，也不能保存 solved MPH。这样实现审计面对的是未求解模型，而不是求解过程已经修改过的对象。

实际生成代码：

- [`iter001_build.java`](https://github.com/aoyang17/PaperSim/blob/main/docs/mvp/kobayashi1993/assets/code/iter001_build.java)
- [`iter001_solve.java`](https://github.com/aoyang17/PaperSim/blob/main/docs/mvp/kobayashi1993/assets/code/iter001_solve.java)

## 2. 从 IR 到 COMSOL 的映射

| IR 内容 | COMSOL 对象 | 审计内容 |
|---|---|---|
| 参数 | Parameters | 名称、表达式、单位、描述 |
| 本构/辅助关系 | Variables | 表达式、Description、分组 |
| 控制方程 | General Form PDE | dependent variable、flux/source 单位 |
| 边界条件 | physics feature | 类型、选择集、表达式 |
| 初始条件 | physics feature | 类型、表达式、作用域 |
| 网格 | mapped mesh | hmax/hmin、元素数量 |
| solver | Study/Solver | BDF、rtol、最大步长、终点 |
| `delta` | Parametric Sweep | 五组值是否全部保留 |

## 3. MPH 读回

Build 完成后，PaperSim 不从 Java 源码推断结果，而是读取 MPH 内部：

```text
smodel.json
dmodel.xml
model settings
```

读回检查包括：

- 参数是否持久化；
- 变量表达式和 Description 是否正确；
- 物理接口和单位是否正确；
- 参数扫描是否存在；
- 边界和初始条件是否存在；
- 网格是否保留；
- solver 设置和终点是否正确。

实现审计记录写入 `iter001_audit.json`。任一关键项失败时，模型不能进入正式 Solve。

## 4. 本案例意义

这一阶段防止两种常见错误：

1. Java 能编译，但 COMSOL 树中的参数、选择集或单位并不是 IR 要求的值；
2. Solve 实际只运行了默认工况，却误以为参数扫描已经执行。

后续求解确实发现了第二种风险：参数解全部存在，但初始导出只引用了默认 solution。该问题在下一章处理。
