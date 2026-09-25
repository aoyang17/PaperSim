# Yeesuan COMSOL MVP Example

This directory is an **example adapter**, not part of the PaperSim library API. It demonstrates how a user can connect PaperSim's generic solver/executor interfaces to one local COMSOL gateway and scheduler.

## Boundary

PaperSim core defines only:

- `SolverBackend` for model execution;
- `RemoteExecutor` for user-supplied `run`, `upload`, `download`, and `describe` operations;
- `ComsolBackend`, which consumes an injected executor and contains no host, account, instance ID, PEM path, scheduler partition, or remote root.

Everything in this directory is replaceable:

- gateway authentication and instance selection;
- SSH/SCP transport;
- Slurm partition and resource policy;
- local COMSOL installation paths;
- user-owned JSON and environment files.

## User configuration

Copy the templates outside the repository, for example:

```bash
mkdir -p ~/.config/papersim
cp yeesuan_config.example.json ~/.config/papersim/yeesuan_comsol.json
cp yeesuan_mvp.env.example ~/.config/papersim/yeesuan_mvp.env
chmod 600 ~/.config/papersim/yeesuan_comsol.json ~/.config/papersim/yeesuan_mvp.env
```

Fill in the gateway account, instance ID, identity path, scheduler partition, and remote COMSOL paths in the copied files. Never commit real configuration or credentials.

## Build the solver

```python
from adapter import build_backend
from papersim import Engine

solver = build_backend(
    config="~/.config/papersim/yeesuan_comsol.json",
    password_file=None,  # direct PEM mode
    suite="full",
)

engine = Engine.open(
    "/path/to/PaperSimWorkspace",
    solvers={"comsol": solver},
)
run = engine.run(model_id, backend="comsol")
```

The library never reads this configuration. The caller creates the executor and injects it into `Engine`.

## Adapter contract

A custom executor must implement:

```python
class Executor:
    def run(self, command, *, timeout=60): ...
    def upload(self, local_path, remote_path, *, timeout=1800): ...
    def download(self, remote_path, local_path, *, timeout=1800): ...
    def describe(self): ...
```

`run`, `upload`, and `download` return `papersim.RemoteResult`. `describe` returns non-secret metadata recorded in the Run evidence.

## Authentication modes

The example supports two modes:

- **Direct PEM**: both `instance_id` and `identity_file` are configured. Login is `user::instance_id`, password prompts are skipped, and SSH runs with `BatchMode=yes`.
- **Legacy menu/password**: `instance_id` is empty. The example retains the gateway menu and password/2FA flow.

## Verify the example

```bash
YEESUAN_ENV_FILE=~/.config/papersim/yeesuan_mvp.env \
  ./assets/yeesuan-comsol check

YEESUAN_ENV_FILE=~/.config/papersim/yeesuan_mvp.env \
  ./assets/yeesuan-comsol probe
```

A successful probe is not a successful simulation. Solver runs still require Slurm completion, clean COMSOL logs, nonempty artifacts, and PaperSim numerical acceptance.
