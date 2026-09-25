# 外部 Solver 接口

PaperSim 库不内置任何具体集群、网关、账号、实例 ID、PEM、分区或远端路径。库只定义接口，用户负责提供本地执行实现。

## 1. SolverBackend

`SolverBackend` 描述一个求解器的生命周期：

```text
validate
build
submit
status
collect
```

用户可以通过 `Engine.open(..., solvers={...})` 注册自己的 backend。

## 2. RemoteExecutor

当求解器运行在外部环境时，可以实现 `RemoteExecutor`：

```python
class Executor:
    def run(self, command, *, timeout=60): ...
    def upload(self, local_path, remote_path, *, timeout=1800): ...
    def download(self, remote_path, local_path, *, timeout=1800): ...
    def describe(self): ...
```

`describe()` 只返回非敏感执行元数据，例如 executor 名称、solver version 和环境标识。

## 3. ComsolBackend

`ComsolBackend` 接收用户注入的 `RemoteExecutor`：

```python
backend = ComsolBackend(
    executor,
    remote_root="/user/owned/case/root",
    suite="full",
)
```

库代码不知道 gateway、实例 ID 或 Slurm 分区，也不知道本地配置文件在哪里。

## 4. Yeesuan MVP 样例

仓库中的：

```text
examples/mvp/yeesuan_comsol/
```

展示了一种可删除、可替换的实现方式，包含：

- 外部配置模板；
- SSH/SCP adapter；
- Slurm 脚本示例；
- PEM 直连模式；
- 用户注入 backend 的示例。

它不属于 `papersim` Python package，也不是 PaperSim 的全局默认配置。

## 5. 安全边界

真实配置必须放在仓库外，并满足：

```text
config file mode = 0600
password file mode = 0600 when used
private key not committed
host / instance / partition not hard-coded in physics code
```

PaperSim 的物理模型、IR 和报告只记录非敏感的 solver 元数据，不保存凭据。
