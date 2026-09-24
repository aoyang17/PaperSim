# Remote COMSOL Job Workflow

This document defines a portable gateway workflow. Site-specific values belong in an external configuration file and must not be committed.

## Configuration contract

```json
{
  "ssh": {
    "host": "gateway.example.org",
    "port": 22,
    "user": "gateway-user",
    "instance_selection": "1",
    "instance_id": "",
    "identity_file": "~/.ssh/remote_comsol_ed25519",
    "host_key_policy": "strict"
  },
  "remote": {
    "environment_script": "~/remote-comsol/env.sh",
    "comsol_executable": "~/remote-comsol/bin/comsol",
    "remote_case_root": "~/papersim_cases"
  }
}
```

Keep the real configuration and password files outside the repository with mode `0600`.

## Probe

```bash
SKILL=/path/to/PaperSim/skills/yeesuan-comsol
"$SKILL/assets/yeesuan-comsol" check
"$SKILL/assets/yeesuan-comsol" probe
```

Confirm the remote identity, home directory, COMSOL version, scheduler availability, and partitions before uploading anything.

## Transfer

```bash
"$SKILL/assets/yeesuan-comsol" mkdir '~/papersim_cases/PROJECT/input'
"$SKILL/assets/yeesuan-comsol" upload ./case-input.tar.gz '~/papersim_cases/PROJECT/input/case-input.tar.gz'
"$SKILL/assets/yeesuan-comsol" download '~/papersim_cases/PROJECT/results/result.mph' ./result.mph
```

Compare local and remote SHA-256 values. If a transfer stalls, do not blindly resubmit.

## Submit and monitor

```bash
"$SKILL/assets/yeesuan-comsol" submit '~/papersim_cases/PROJECT' 'slurm/comsol_job.slurm'
"$SKILL/assets/yeesuan-comsol" status JOB_ID
"$SKILL/assets/yeesuan-comsol" tail '~/papersim_cases/PROJECT/logs/comsol_batch_JOB_ID.log'
```

After a terminal scheduler state, require:

- `sacct` reports `COMPLETED|0:0`;
- Slurm stderr has no fatal diagnostic;
- the COMSOL log has no error, exception, or license failure;
- requested MPH and exported data are present and nonempty;
- output hashes match after transfer.

A scheduler completion alone is not a numerical result.
