# Kobayashi 1993 iter001 numerical audit plan

This table set was fixed before modifying the solve/export Java. The physics equations, model variables, boundary conditions, and initial conditions remain unchanged from approved `iter001_ir.json`.

## Equation-to-feature mapping

| Equation | Classification | Mathematical form | COMSOL feature | Named support quantities |
|---|---|---|---|---|
| Eq. (3) | control | `tau*p_t = div(Gamma) + p(1-p)(p-1/2+m(T))` | General Form PDE `gp` | `GammaPx`, `GammaPy`, `phaseSource` |
| Eq. (4), driving force | constitutive | `m(T) = alpha/pi*atan(gamma*(Teq-T))` | Variables `v_source` | `mT` |
| Eq. (4), anisotropy | constitutive | `epsilon(theta) = epsbar*(1+delta*cos(jmode*(theta-theta0)))` | Variables `v_interface` | `epsilon`, `epsilonTheta` |
| Eq. (5) | control | `T_t = D*lap(T) + Klatent*p_t` | General Form PDE `gT` | `heatFluxX`, `heatFluxY`, `latentSource` |

## Parameters and sensitivity cases

| Case ID | `delta` | `hmesh` (m) | `maxStep` (s) | `noiseAmp` | `noiseSeed` | `R0` (m) | `tfinal` (s) | Purpose |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `baseline_delta000` | 0 | 0.03 | 0.0002 | 0.01 | 1993 | 0.15 | 1.4 | Fig. 7 baseline |
| `baseline_delta005` | 0.005 | 0.03 | 0.0002 | 0.01 | 1993 | 0.15 | 1.4 | Fig. 7 sweep |
| `baseline_delta010` | 0.01 | 0.03 | 0.0002 | 0.01 | 1993 | 0.15 | 1.4 | Fig. 7 sweep |
| `baseline_delta020` | 0.02 | 0.03 | 0.0002 | 0.01 | 1993 | 0.15 | 1.4 | Fig. 7 sweep and no-noise baseline reference |
| `baseline_delta050` | 0.05 | 0.03 | 0.0002 | 0.01 | 1993 | 0.15 | 1.4 | Fig. 7 sweep |
| `control_delta020` | 0.02 | 0.03 | 0.0002 | 0 | 1993 | 0.15 | 0.8 | Sensitivity baseline |
| `mesh_fine` | 0.02 | 0.02 | 0.0002 | 0 | 1993 | 0.15 | 0.8 | Mesh convergence |
| `timestep_fine` | 0.02 | 0.03 | 0.0001 | 0 | 1993 | 0.15 | 0.8 | Time-step convergence |
| `seed_small` | 0.02 | 0.03 | 0.0002 | 0 | 1993 | 0.12 | 0.8 | Initial-radius robustness |
| `seed_large` | 0.02 | 0.03 | 0.0002 | 0 | 1993 | 0.18 | 0.8 | Initial-radius robustness |

## Variables and physical quantities

| Quantity | COMSOL expression | Unit | Description |
|---|---|---|---|
| `tipY` | `maxop1(if(p>=0.5,y,0))` | m | Maximum vertical solid coordinate |
| `halfWidth` | `maxop1(if(p>=0.5,abs(x-xCenter),0))` | m | Maximum horizontal solid coordinate |
| `pMin` | `minop1(p)` | 1 | Minimum phase field |
| `pMax` | `maxop1(p)` | 1 | Maximum phase field |
| `enthalpyInvariant` | `intop1(T-Klatent*p)` | m^2 | Post-processing enthalpy invariant |

## Boundary, initial, mesh, and solver settings

| Item | Setting |
|---|---|
| Boundary | Zero flux for `p` and `T` |
| Initial | Smooth circular phase seed of radius `R0`; `T=0` |
| Mesh | Mapped `300 x 300` for baseline; `600 x 600` equivalent spacing for `mesh_fine` |
| Study | Parametric sweep in `delta` |
| Time solver | BDF, order 2, relative tolerance `1e-3` |
| Output times | `0, 0.01, ..., 1.4` s |
| Comparison times | `0.2, 0.8, 1.4` s |

## Export contract

| Stage | Artifact | Content |
|---|---|---|
| Existing parameter solve | `iter001_solved.mph` | Five stored solutions `sol2/su1` through `sol2/su5` |
| Export-only run | `iter001_global_delta*.csv` | Global histories for each `delta` |
| Export-only run | `iter001_fields_delta*.csv` | `p` and `T` at comparison times for each `delta` |
| Sensitivity runs | `<variant>_global.csv` | At least final `tipY`, `pMin`, `pMax`, and enthalpy history |

## Acceptance mapping

| Acceptance ID | Metric source |
|---|---|
| `phase_lower_bound` | Minimum `pMin` over all exported baseline sweeps |
| `phase_upper_bound` | Maximum `pMax` over all exported baseline sweeps |
| `enthalpy_conservation` | Maximum relative drift of `enthalpyInvariant` |
| `mesh_tip_convergence` | `abs(tipY_mesh_fine-tipY_delta020)/abs(tipY_delta020)` |
| `timestep_tip_convergence` | `abs(tipY_timestep_fine-tipY_delta020)/abs(tipY_delta020)` |
| `seed_tip_robustness` | `(max(seed tips)-min(seed tips))/abs(mean(seed tips))` |
| `anisotropy_increases_tip_growth` | `tipY(delta=.05,t=1.4)/tipY(delta=0,t=1.4)` |
| `fourfold_directionality` | `tipY(delta=.05,t=1.4)/halfWidth(delta=.05,t=1.4)` |
| `fig7_silhouette_overlap` | Mean IoU of exported contours against digitized Fig. 7 masks |
| `fig7_contour_distance` | Mean normalized Chamfer distance against digitized Fig. 7 masks |
