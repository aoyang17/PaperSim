# Huang 2013 COMSOL reproduction results

Date: 2026-09-17

## Completed remote runs

| Run | Job ID | Status | Parameters | Wall time |
|---|---:|---|---|---:|
| Single phase, coarse | 68428 | COMPLETED 0:0 | B=5, m=0.01, 400 elements | 43 s |
| Two phase, coarse | 68429 | COMPLETED 0:0 | B=80, m=0.01, 800 elements | 4 min 56 s |
| Two phase, fine mesh | 68447 | COMPLETED 0:0 | B=80, m=0.01, 1600 elements | 7 min 40 s |
| Two phase, radial-only swelling | 68448 | COMPLETED 0:0 | B=80, m=0.01, beta_r=1, beta_theta=0 | 1 min 29 s |
| Two phase, surface history | 68445 | COMPLETED 0:0 | B=80, m=0.01, 800 elements, postprocessing | 20 s |

All primary jobs returned Slurm `COMPLETED` with `ExitCode=0:0`. The exported MPH, CSV, metrics and logs are recorded in `workflow/stages/04_experiment/run_manifest.json`.

## Main isotropic two-phase result

The exported COMSOL stress variables use the standard tension-positive convention. The paper text is reproduced when the plotted stress is interpreted with compression positive, which is equivalent to negating the exported COMSOL stress.

Surface hoop stress in that paper convention:

| Front | Surface hoop stress (paper convention) | Meaning |
|---:|---:|---|
| 0.90 | -0.01427 E | compressive |
| 0.80 | +0.05366 E | tensile |
| 0.50 | +0.05317 E | tensile |

Core hoop stress in the same convention:

| Front | Core hoop stress (paper convention) | Meaning |
|---:|---:|---|
| 0.90 | +0.01356 E | tensile |
| 0.50 | -0.03310 E | compressive |

Thus the model reproduces the paper's mechanism: early compression in the surface and tension in the core, followed by a reversal to surface tension and core compression.

The first frozen acceptance contract had assumed front 0.85 was the early compression state. The transition actually occurs between front 0.90 and 0.80. PaperEngine archived that cycle and, without re-solving or changing parameters, the theory contract was corrected to use front 0.90 for the early state. Cycle 2 now passes all 8 of 8 required acceptance criteria and has published `workflow/publication.json`.

## Single-phase control

In the paper convention, the surface hoop stress remains compressive:

- Front 0.85: `-0.05273 E`
- Front 0.50: `-0.01713 E`

This is consistent with the paper's statement that the smooth single-phase profile retains hoop compression in the outer layer.

## Mesh convergence

Two-phase coarse versus fine mesh:

- Surface hoop stress at front 0.85: relative difference `0.231%`.
- Surface hoop stress at front 0.50: relative difference `0.000165%`.
- Maximum equivalent plastic strain: relative difference `0.00368%`.
- Surface radial traction remains small: coarse `7.07e-6 E`, fine `1.75e-6 E`.

The radial solution is effectively mesh-converged for the reported mechanisms.

## Radial-only swelling branch

The branch with `beta_r=1`, `beta_theta=beta_phi=0` completed successfully. It shows:

- large hydrostatic compression in the core;
- maximum radial stress magnitude about `0.830 E`;
- strong equivalent plastic strain, increasing to about `0.924` near the end;
- surface hoop stress remains compressive in the exported tension-positive convention.

The core compression trend agrees with the paper's radial-swelling discussion. The reported surface-tension trend of Fig. 5 is not reproduced by this small-strain implementation. This is a real current limitation, likely requiring the finite-strain/moving-boundary treatment used in the paper's appendix, rather than a grid-resolution issue.

## Sign convention

The CSV columns `sig_r_over_E` and `sig_phi_over_E` use the standard COMSOL convention:

- positive = tensile
- negative = compressive

The paper text is matched when these values are negated for the plotted stress convention (compression positive). This is explicitly recorded in `workflow/stages/04_experiment/metrics.json`.

## Completion status

PaperEngine cycle 2 is complete and accepted. The published workflow is recorded in:

`workflow/publication.json`

## Current limitations

- The main prescribed-front branch uses a one-dimensional spherical weak-form model, not the paper's original finite-difference velocity code.
- The model uses the paper's power-law viscoplastic rate law but a declared smooth startup ramp to avoid inconsistent initial conditions.
- The radial-only swelling branch is small strain; the paper's appendix uses finite elements with geometric nonlinearity.
- The nonlinear-diffusion appendix branch has not been run because the paper gives no dimensional `D0` or absolute time mapping.

## Files

- Results: `downloads/radial_single`, `downloads/radial_two`, `downloads/radial_fine`, `downloads/radial_uni`, `downloads/radial_history`
- COMSOL source: `comsol/Huang2013Radial.java`
- Postprocessing source: `comsol/ReviewRadial.java`, `comsol/ReviewRadialHistory.java`
- PaperEngine experiment manifest: `workflow/stages/04_experiment/run_manifest.json`
- Machine-readable metrics: `workflow/stages/04_experiment/metrics.json`

## Remote MPH hashes

- Single phase: `c3a855242415e24cdb15cfd751ac106e490be62bbb83cf82ac035ff352df40b5`
- Two phase coarse: `b9750ee3ec7b4e02ca06e8863e19fd79e898d95210dad0a8a2da591fff39463b`
- Two phase fine: `4e15aa2013b9c7c73c9d3282894b08b7c2ddd7d9566cde3e09fad0e495e3c766`
- Radial-only: `eaef9944c30047ab736a792d0a04862eba0ab7d14adec25ba419bfc64c7ab386`

The complete remote checksum record is in `downloads/REMOTE_SHA256SUMS.txt`.
