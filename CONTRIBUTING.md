# Contributing to PaperSim

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[test,pdf,extraction]'
python3 -m pytest -m "not pdf and not comsol"
```

## Required workflow

Every new feature must include:

1. a deterministic Python implementation;
2. a unit or contract test in `tests/features/`;
3. at least one negative/fail-closed case;
4. an end-to-end fixture using the fake solver where applicable;
5. documentation when it changes a public CLI, schema, artifact, state gate, or file name.

Do not make an LLM, network service, private host, credential, or local absolute path a prerequisite for the core test suite.

## Model changes

COMSOL Java changes must follow `skills/comsol-modeling/SKILL.md` and preserve:

- control equations only in PDE/ODE interfaces;
- constitutive and auxiliary relations as named Variables with descriptions;
- one Parametric Sweep for declared parameter variations;
- build-only and solve-only source separation;
- persisted-unit and MPH-readback checks.

## Pull requests

Before opening a pull request run:

```bash
python3 -m pytest -m "not pdf and not comsol"
python3 -m pytest -m pdf
python3 -m pytest -m comsol
git status --short
```

Mark PDF and COMSOL suites as environment-dependent in the pull request description. Never commit credentials, private keys, MPH files, or generated result data.
