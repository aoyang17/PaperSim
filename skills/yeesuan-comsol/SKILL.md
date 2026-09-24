---
name: yeesuan-comsol
description: Connect to a configured remote COMSOL gateway, transfer a PaperSim case, submit Slurm jobs, monitor them, and verify/download results. Use when COMSOL is behind an SSH gateway or HPC login service; do not use for local COMSOL installations or unrelated clusters.
---

# Remote COMSOL Gateway

Use a configured SSH gateway as a separate execution environment. A successful login, transfer, or `sbatch` response is never sufficient evidence of a successful simulation.

## Connection boundary

- Keep host names, accounts, ports, instance identifiers, remote roots, and identity paths in an external mode-`0600` configuration file.
- Read passwords and 2FA secrets only from external mode-`0600` files.
- Never put credentials, private keys, or site-specific infrastructure values in this repository.
- Verify host-key fingerprints through a trusted channel before accepting a new host key.
- Treat saved instance identifiers as hints; confirm the active environment before running jobs.

## Before submitting

1. Run the wrapper's `check` and `probe` commands.
2. Confirm the remote user, environment script, COMSOL executable/version, scheduler, and partitions.
3. Create a dedicated remote project directory with `input/`, `slurm/`, `logs/`, and `results/`.
4. Upload inputs and Slurm scripts without overwriting existing results.
5. Record SHA-256 hashes before and after transfers.

## Operate safely

1. Keep connection logic in the gateway adapter, not in a physics model.
2. Do not assume a partition or resource request is portable; discover current scheduler state.
3. Submit through the canonical wrapper and monitor both `squeue` and `sacct`.
4. Inspect Slurm stdout/stderr and the COMSOL batch log.
5. Declare success only when the scheduler reports `COMPLETED|0:0`, the COMSOL log has no fatal diagnostic, and every expected artifact exists and is nonempty.
6. Record command, environment, job ID, elapsed time, exit code, input hash, and output hash in the PaperSim Run evidence.

Use `connection.example.json` and `comsol.env.example` as field templates only. Real configuration files must remain outside the repository.
