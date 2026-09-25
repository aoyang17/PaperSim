# Yeesuan Gateway Workflow Example

This workflow is user-owned sample code. It is not a PaperSim package default or a required deployment layout.

## 1. Prepare configuration

Copy `yeesuan_config.example.json` to a local file outside the repository and fill in:

- gateway host, port, and account;
- current instance ID and identity file;
- COMSOL environment script and executable;
- a remote case root owned by the user.

For direct PEM mode, set both `instance_id` and `identity_file`. For legacy menu/password mode, leave `instance_id` empty and provide a mode-0600 password file.

## 2. Inject the executor

```python
from adapter import build_backend

solver = build_backend(
    config="/path/to/yeesuan_comsol.json",
    password_file=None,
)
```

Register it with PaperSim:

```python
engine = Engine.open(workspace, solvers={"comsol": solver})
```

PaperSim `Engine.run` deliberately does not load a connection profile or construct this backend automatically.

## 3. Probe

```bash
YEESUAN_ENV_FILE=/path/to/yeesuan_mvp.env \
  ./assets/yeesuan-comsol probe
```

Confirm the remote user, COMSOL version, scheduler, and partition before submitting work.

## 4. Submit and monitor

```bash
YEESUAN_ENV_FILE=/path/to/yeesuan_mvp.env \
  ./assets/yeesuan-comsol submit '~/path/to/project' 'slurm/comsol_job.slurm'

YEESUAN_ENV_FILE=/path/to/yeesuan_mvp.env \
  ./assets/yeesuan-comsol status JOB_ID
```

Completion requires `COMPLETED|0:0`, clean logs, and nonempty outputs. Scheduler completion alone is not numerical acceptance.
