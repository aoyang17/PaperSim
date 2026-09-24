---
name: comsol-modeling
description: Build or revise COMSOL Java models with named parameters, staged constitutive variables, explicit physics interfaces, and auditable equation-to-feature mapping. Use for COMSOL Java/LiveLink model construction, weak-form equations, coupled multiphysics, boundary conditions, solver setup, and debugging where the model must remain understandable and independently verifiable.
metadata:
  short-description: Build readable, auditable COMSOL Java models
---

# COMSOL Modeling

Use this skill when translating a paper or derivation into a COMSOL Java
model. The primary requirement is not merely that COMSOL runs, but that every
parameter, constitutive quantity, boundary condition, and solver setting can
be traced back to a named symbol and a paper equation.

This skill is self-contained. It records a portable authoring style and does
not require any particular Java file, repository, machine path, or remote
platform. Existing model files may be consulted as optional examples, but a
model must remain understandable from the equations and tables in the target
work itself.

Do not make a local absolute path, a personal workspace, or an external Java
source a prerequisite for applying this skill. Substitute the target model's
own symbol names and values for the illustrative examples below.

For remote execution and transfer, use a separate environment-specific skill
when one is available. Do not duplicate connection or scheduler instructions
here.

# Hard constraints R1-R3 (highest priority)

You are generating, modifying, or reviewing a COMSOL model. These rules are
mandatory. If a user request conflicts with them, state the conflict before
proceeding; do not silently violate the rules. If any later section, example,
skeleton, or legacy note conflicts with this section, this section prevails.

## R1 Separation of control equations and constitutive relations

### Definitions

- Control equations are conservation laws, balance laws, and evolution
  equations, for example:
  - `∂φ/∂t + ∇·J = S`
  - `∇·σ + F = 0`
  - `du/dt = f`
- Constitutive relations are material responses, closure relations, equations
  of state, reaction rates, and auxiliary algebraic relations, for example:
  - `J = -D∇c`
  - `q = -k∇T`
  - `σ = C:ε`
  - `R = k c_A c_B`
  - `ρ = pM/(RT)`

### MUST

1. Put only control equations into the COMSOL PDE/ODE modules or the
   corresponding physics interface.
2. Define every constitutive relation, material law, equation of state,
   reaction rate, and auxiliary relation under
   `Component > Definitions > Variables`.
3. If a PDE/ODE source term, flux, or coefficient comes from a constitutive
   relation, define a named variable for it first and reference that variable
   from the PDE/ODE.
4. Boundary and initial conditions remain in the PDE/ODE or physics interface.
   If their expressions contain constitutive relations, they must reference
   variables already defined under `Component > Definitions > Variables`.
5. Every model output must contain an `equation_classification` table that
   classifies each equation as one of:
   `control`, `constitutive`, `auxiliary`, `boundary`, or `initial`.
6. Every Variable must have a clear human-readable description in the
   Variable Description field. In COMSOL Java use the three-argument form
   `.set(name, expression, description)`. Never leave the Description field
   blank or use only a code identifier as the description.
7. Every PDE/ODE module must declare units for its dependent variables and
   for its flux/source terms. Use the interface unit properties such as
   `DependentVariableQuantity`, `CustomDependentVariableUnit`,
   `SourceTermQuantity`, and `CustomSourceTermUnit` where supported. For a
   weak-form interface, declare the residual/flux unit explicitly in the
   output table and scale the weak expression consistently. A PDE/ODE module
   without declared variable and flux/source units is incomplete.

### NEVER

1. Do not inline constitutive expressions directly in PDE/ODE source terms,
   fluxes, or coefficients.
2. Do not disguise a constitutive relation as a control equation and write it
   into a PDE/ODE module.
3. Do not mix material parameters, constitutive variables, and intermediate
   variables inside PDE/ODE expressions without declaring them.

### Positive example

Variables:

```text
q = -k*Tx
```

PDE:

```text
f = q
```

### Negative example

PDE:

```text
f = -k*Tx
```

### Legacy native-physics rule

Native COMSOL physics features may be used as control-equation carriers, or as
containers whose material response is supplied exclusively through named
variables, only when this does not hide an undeclared constitutive relation.
A native constitutive node that silently encodes a material law is not a
substitute for the required Variables definition. If the native feature and
R1 cannot both be satisfied, use a PDE/ODE plus Variables formulation or state
the conflict explicitly.

## R2 Parameter changes must use Parametric Sweep and one MPH

### MUST

1. Perform every parameter variation through
   `Parameters` plus `Study > Parametric Sweep`.
2. A parameter-sweep task must generate or modify exactly one `.mph` file.
3. Solve all parameter combinations inside the same `.mph`; keep the result
   sets in that same model file.
4. If the parameters come from a file, read the parameter list through
   Parametric Sweep. Do not duplicate one `.mph` per parameter value.
5. Every model output must contain a `parameter_sweep` table with:
   - paper symbol;
   - COMSOL parameter name;
   - value or range;
   - sweep study name.

### NEVER

1. Do not create a separate `.mph` for each parameter value.
2. Do not output files such as `model_L1.mph`, `model_L2.mph`, or
   `model_L3.mph`.
3. Do not bypass Parametric Sweep without recording and explaining the reason.

## R3 Report and nomenclature rules

### MUST

1. When extracting article equations, use human-readable mathematical form,
   preferably LaTeX display equations, for example:
   `\nabla\cdot(-k\nabla T)=Q`.
2. Preserve the source paper's definitions, symbols, numbering, and meaning.
3. Every report must provide a Nomenclature table containing at least:
   - source-paper symbol;
   - mathematical meaning;
   - unit;
   - COMSOL variable name;
   - source equation or source section.
4. If the source symbol differs from the COMSOL variable name, map them in the
   Nomenclature table. Do not replace the source symbol in the report.
5. Preserve vectors, tensors, superscripts, subscripts, and bold notation as
   close to the source as possible.
6. If the source does not provide a unit or definition, write `原文未给`.
   Do not invent it.

### NEVER

1. Do not replace the mathematical equations in a report with raw COMSOL code
   expressions.
2. Do not silently normalize or unify source symbols.
3. Do not omit the Nomenclature mapping.

### Positive example

Eq. (3): `\nabla\cdot(-k\nabla T)=Q`

Nomenclature:

| Source symbol | Meaning | Unit | COMSOL variable | Source |
|---|---|---|---|---|
| T | temperature | K | T | Eq. (3) |
| k | thermal conductivity | W/(m·K) | k | Eq. (3) |

### Negative example

`comp1.k*(Tx)` is not acceptable as the main report equation.

## Mandatory workflow

1. Read the paper or requirements and extract equations.
2. Classify every equation as `control`, `constitutive`, `auxiliary`,
   `boundary`, or `initial`.
3. Put control equations into PDE/ODE interfaces.
4. Put constitutive and auxiliary relations into Variables.
5. Put reusable numbers into Parameters.
6. Put parameter changes into Parametric Sweep.
7. Generate the report and Nomenclature table.
8. Run the self-check before output.

## Mandatory output format

When producing a model plan, model changes, review, or report, use exactly this
order:

1. `equation_classification`
2. `comsol_tree_changes`
3. `variables_definitions`
4. `pde_ode_settings`
5. `parameters`
6. `parametric_sweep`
7. `report_nomenclature`
8. `self_check`

The `variables_definitions` table must contain at least Name, Expression, Unit
and Description. The `pde_ode_settings` table must contain the dependent
variable unit and the flux/source or weak-residual unit for every PDE/ODE
module.

## Mandatory self-check

- [ ] No constitutive expressions are inlined in PDE/ODE settings.
- [ ] All constitutive relations are defined in Variables.
- [ ] PDE/ODE settings reference only named Variables for constitutive terms.
- [ ] Every Variable has a non-empty human-readable Description.
- [ ] Every PDE/ODE module declares dependent-variable and flux/source units.
- [ ] Parameter variations use Parametric Sweep.
- [ ] Only one `.mph` is generated or modified per sweep task.
- [ ] Reports use human-readable mathematical equations.
- [ ] Reports preserve source symbols, numbering, and definitions.
- [ ] Nomenclature completely maps source symbols to COMSOL variables.
- [ ] Anything uncertain is marked `NEEDS_REVIEW`; do not guess.

## Non-negotiable style

1. Declare reusable numbers in `model.param()` with units.
2. Give every physical quantity a named COMSOL variable, with constitutive and auxiliary quantities under `Component > Definitions > Variables`.
3. Build constitutive equations in layers. Never paste a paper equation plus
   all material laws plus boundary formulas into one monolithic expression.
4. Use native COMSOL physics features only for control/balance equations or when their material response is supplied exclusively through named variables; otherwise use PDE/ODE plus Variables.
5. Separate different dependent variables into separate `WeakFormPDE`
   interfaces unless a mixed formulation is genuinely required.
6. Keep build-only Java deterministic. Save an unsolved MPH and solve it in a
   separate batch job.
7. After building, inspect the persisted feature properties, units, selections,
   initial values, and solver lists. A successful Java compilation is not a
   valid model check.

## 1. Portability rules

Apply these rules before writing any COMSOL source:

1. Store the physics in the model itself, not in an external Java file.
2. Do not hard-code a machine-specific path such as a home directory, drive
   letter, login-node scratch path, or repository location.
3. Treat all examples in this skill as illustrative naming patterns. Replace
   their symbols and values with the target problem's symbols and values.
4. Put run-specific paths, credentials, partitions, and remote locations in
   external execution configuration, not in the constitutive model.
5. Keep the Java class reproducible from its own parameter table, variable
   table, equation table, boundary table, and solver table.
6. If an external example is used, cite it in comments or provenance notes but
   do not make loading it necessary to build or understand the model.

## 2. Translate the paper into four tables first

Before writing Java, make four tables. The following entries are illustrative; substitute the target problem’s names and values.

### Parameter table

Record symbol, COMSOL name, value, unit, meaning, and source equation.

| Paper symbol | COMSOL name | Value | Unit | Meaning |
|---|---:|---:|---|---|
| `A` | `r_particle` | 70 | nm | particle radius |
| `D` | `D_Si` | `2e-17` | m^2/s | interdiffusion coefficient |
| `kappa` | `k_c` | `2e-9` | J/m | gradient-energy coefficient |
| `Omega` | `omega_Si` | 2.6 | 1 | regular-solution parameter |
| `beta` | `beta` | 0.5874 | 1 | chemical-expansion coefficient |

Use:

```java
model.param().set("r_particle", "70[nm]");
model.param().set("D_Si", "2E-17[m^2/s]");
model.param().set("k_c", "2E-9[J/m]");
model.param().set("omega_Si", "2.6");
model.param().set("beta", "0.5874");
```

Do not repeat `70[nm]`, `2e-9[J/m]`, or other reusable values inside a weak
expression. Refer to the parameter name.

### Variable table

List every intermediate quantity before writing the weak form.

| Layer | COMSOL variable | Expression | Purpose |
|---|---|---|---|
| Normalization | `SOC` | `u2/c_max_Si` | dimensionless concentration |
| Transport | `M_Si` | `D_Si/(c_max_Si*R_const*T_0)*SOC*(1-SOC)` | mobility |
| Elastic property | `E_Si` | `160[GPa]-120[GPa]*SOC` | concentration-dependent modulus |
| Elastic property | `v_Si` | `0.23` | Poisson ratio |
| Plasticity | `Sigma_Si` | `1.5[GPa]` | yield strength |
| Plasticity | `H_Si` | `1[GPa]` | hardening modulus |
| Boundary | `c_boundary` | `c0+0.9*(c_max_Si-c0)*min(t/t_ramp,1)` | surface value |

### Equation table

For each equation, list the strong form, weak form, dependent variable, test
function, and native COMSOL feature.

| Equation | Strong form | Weak form | COMSOL object |
|---|---|---|---|
| Li transport | `c_t = div(M grad(mu))` | `∫ r c_t q + r M mu_R q_R` | `physics("w")` |
| Chemical potential | `mu = f'(c) - kappa lap(c) + mu_el` | `∫ r(mu-f'-mu_el) p - k_c r c_R p_R` | `physics("w2")` |
| Intercalation strain | prescribed volumetric expansion | native eigenstrain | `IntercalationStrain` |
| Plasticity | rate-independent J2 | native plastic flow | `Plasticity` |

### Boundary and initial-condition table

List every boundary, selection, value, and physical role before coding.

| Boundary | Selection | Condition | COMSOL feature |
|---|---|---|---|
| outer surface | entity 2 | `c=c_boundary` | `DirichletBoundary` |
| axis | entity 1 | regular symmetry | native symmetry |
| outer surface | entity 2 | traction free | `Free` |
| initial state | domain | `u2=c0`, `u3=mu0` | `Initial Values` or `model.init()` |

## 3. Java construction order

Use this order. It keeps the source readable and makes failures local.

```text
1. imports and class
2. model creation and labels
3. parameters with physical units
4. component and geometry
5. selections
6. variable groups
7. physics interfaces
8. constitutive/material properties
9. weak-form equations
10. initial conditions and constraints
11. mesh
12. studies and solver settings
13. result datasets and fixed expressions
14. save the unsolved MPH
```

Do not interleave unrelated settings. Parameters should not be buried between
weak equations. Material properties should be set after their variables exist.
Boundary features should be configured after their selections are named.

## 4. Parameter grouping style

Group parameters by physical meaning:

```java
// Geometry and fields
model.param().set("r_particle", "70[nm]");
model.param().set("c_max_Si", "366800[mol/m^3]");

// Transport
model.param().set("D_Si", "2E-17[m^2/s]");
model.param().set("k_c", "2E-9[J/m]");
model.param().set("omega_Si", "2.6");

// Mechanics and chemistry
model.param().set("beta", "0.5874");
model.param().set("t_ramp", "5[s]");

// Time integration
model.param().set("delta_t", "2.45[s]");
```

Rules:

- Use SI units in parameter strings unless a paper value is clearer.
- Keep a parameter's name stable across build, audit, and report files.
- Never use a parameter name for two different concepts.
- If a value is derived, make it a variable rather than a parameter.
- Add a short comment linking each group to the corresponding paper section.

## 5. Variable layering

Create one or more variable groups whose names describe the layer.

Every Variable must use the three-argument form:

```java
model.component("comp1").variable("var1")
     .set("SOC", "u2/c_max_Si", "normalized Li concentration");
```

The third argument is the COMSOL Description field and must be physically
meaningful. Do not leave it blank.


### Layer A: normalization and fields

```java
model.component("comp1").variable().create("var1");
model.component("comp1").variable("var1")
     .set("SOC", "u2/c_max_Si", "normalized Li concentration");
```

### Layer B: transport coefficients

```java
model.component("comp1").variable("var1")
     .set("M_Si", "D_Si/(c_max_Si*R_const*T_0)*(SOC*(1-SOC))",
          "Li mobility");
model.component("comp1").variable("var1")
     .set("c_boundary", "c0+0.9*(c_max_Si-c0)*min(t/t_ramp,1)",
          "surface concentration boundary value");
```

### Layer C: geometry and kinematics

```java
model.component("comp1").variable("var3")
     .set("R_hat", "R/r_particle", "normalized radial coordinate");
model.component("comp1").variable("var3")
     .set("r_current", "R+A*ur", "current radial coordinate");
model.component("comp1").variable("var3")
     .set("fr", "1+A*urx", "radial stretch");
model.component("comp1").variable("var3")
     .set("ft", "if(R>A*1e-12,1+A*ur/R,fr)",
          "hoop stretch with axis regularization");
```

### Layer D: constitutive properties

```java
model.component("comp1").variable("var2")
     .set("E_Si", "160[GPa]-120[GPa]*SOC",
          "concentration-dependent Young modulus");
model.component("comp1").variable("var2")
     .set("v_Si", "0.23", "Poisson ratio");
model.component("comp1").variable("var2")
     .set("Sigma_Si", "1.5[GPa]", "yield strength");
model.component("comp1").variable("var2")
     .set("H_Si", "1[GPa]", "hardening modulus");
```

### Layer E: nonlinear constitutive laws

Break a complex law into physically named intermediates.

```java
// Elastic strain invariants
model.component("comp1").variable("var2")
     .set("u_el2", "solid.eel11^2+solid.eel22^2+solid.eel33^2"
                   "+2*(solid.eel12)^2+2*(solid.eel13)^2+2*(solid.eel23)^2",
          "elastic strain invariant");

// Hydrostatic contribution
model.component("comp1").variable("var2")
     .set("S_hydro", "-3*solid.pm", "hydrostatic stress contribution");

// Final driving force; references named terms only
model.component("comp1").variable("var2")
     .set("u_el", "-beta*S_hydro-120[GPa]*u_el2",
          "elastic chemical-potential contribution");
```

Older two-argument variable examples elsewhere in this file are legacy
patterns. Under R1 they must be read as `.set(name, expression, description)`.
A variable definition without a description is incomplete.

Do not write:

```java
// Bad: impossible to inspect term by term
.set("weak", "r*(u2t/c_max_Si)*test(u2)"
            "+r*D_Si/(c_max_Si*R_const*T_0)*SOC*(1-SOC)*u3r*test(u2r)");
```

Instead define `M_Si` first and use it in the weak form.

## 6. Native physics before custom weak forms

Prefer native COMSOL features when the paper law maps directly.

### Solid mechanics

> **R1 priority note:** The native-feature code below is illustrative only. Under the hard constraints, a native constitutive node must not hide an undeclared material law. Any constitutive response used by a native feature must be represented by named variables, or the constitutive law must be moved to a PDE/ODE plus Variables formulation. If the native feature and R1 conflict, R1 prevails and the conflict must be stated.

```java
model.component("comp1").physics().create("solid", "SolidMechanics", "geom1");
model.component("comp1").physics("solid")
     .feature("lemm1").create("ic1", "IntercalationStrain", 1);
model.component("comp1").physics("solid")
     .feature("lemm1").create("plsty1", "Plasticity", 1);
```

Configure properties by name:

```java
model.component("comp1").physics("solid").feature("lemm1")
     .set("E_mat", "userdef");
model.component("comp1").physics("solid").feature("lemm1")
     .set("E", "E_Si");
model.component("comp1").physics("solid").feature("lemm1")
     .set("nu_mat", "userdef");
model.component("comp1").physics("solid").feature("lemm1")
     .set("nu", "v_Si");

model.component("comp1").physics("solid")
     .feature("lemm1").feature("ic1")
     .set("dvolic_mat", "userdef");
model.component("comp1").variable("var2")
     .set("dvolic", "(1+beta*(SOC-c0/c_max_Si))^3-1",
          "volumetric intercalation strain");
model.component("comp1").physics("solid")
     .feature("lemm1").feature("ic1")
     .set("dvolic", "dvolic");

model.component("comp1").physics("solid")
     .feature("lemm1").feature("plsty1")
     .set("sigmags_mat", "userdef");
model.component("comp1").physics("solid")
     .feature("lemm1").feature("plsty1")
     .set("sigmags", "Sigma_Si");
model.component("comp1").physics("solid")
     .feature("lemm1").feature("plsty1")
     .set("Et_mat", "userdef");
model.component("comp1").physics("solid")
     .feature("lemm1").feature("plsty1")
     .set("Et", "H_Si");
```

Before relying on a native property, verify:

- what stress measure it uses;
- whether `Et` means tangent modulus or plastic hardening modulus;
- whether geometric nonlinearity is enabled;
- how the chemical expansion enters the total deformation;
- which variables are stress, strain, and equivalent-stress outputs.

### Weak-form PDEs

Use one `WeakFormPDE` per dependent variable when possible.

```java
model.component("comp1").physics().create("w", "WeakFormPDE", "geom1");
model.component("comp1").physics("w").prop("Units")
     .set("DependentVariableQuantity", "none");
model.component("comp1").physics("w").prop("Units")
     .set("CustomDependentVariableUnit", "mol/m^3");
```

This makes `w` own `u2`; create `w2` for `u3` instead of hiding both fields
inside one weak expression.

## 6.1 PDE/ODE unit declaration

Every PDE/ODE module must declare the units of its dependent variables and
its flux/source or weak-residual terms. Record them in the model and in the
`pde_ode_settings` output table.

Example for a Weak Form PDE:

```java
model.component("comp1").physics("w")
     .prop("Units").set("DependentVariableQuantity", "none");
model.component("comp1").physics("w")
     .prop("Units").set("CustomDependentVariableUnit", "mol/m^3");
model.component("comp1").physics("w")
     .prop("Units").set("SourceTermQuantity", "none");
model.component("comp1").physics("w")
     .prop("Units").set("CustomSourceTermUnit", "mol/(m^3*s)");
```

If a particular PDE/ODE interface does not expose `SourceTermQuantity` or
`CustomSourceTermUnit`, declare the equivalent weak-residual/flux unit in the
output table and scale the weak expression consistently. Unit declaration is
not optional merely because COMSOL can build without it.

## 7. Weak-form writing style

Write the weak form as named physical terms.

### Concentration evolution

Strong form:

```text
c_t = div(M grad(mu))
```

Weak form:

```text
∫ r*(u2t/c_max_Si)*test(u2) + r*M_Si*u3r*test(u2r) = 0
```

Java:

```java
model.component("comp1").physics("w").feature("wfeq1")
     .set("weak", "r*(u2t/c_max_Si)*test(u2)"
                 "+r*M_Si*u3r*test(u2r)");
```

The two terms are:

- `storage`: `r*u2t/c_max_Si`
- `flux`: `r*M_Si*u3r`

### Chemical-potential equation

Strong form:

```text
mu = f'(c) - kappa*lap(c) + mu_el
```

Weak form:

```text
∫ r*u3*test(u3)
 - r*( f'(c)*S + mu_el )*test(u3)
 - k_c*(r*u2r/c_max_Si*test(u3r)) = 0
```

Java:

```java
model.component("comp1").physics("w2").feature("wfeq1")
     .set("weak", "r*u3*test(u3)"
                 "-(r*c_max_Si*R_const*T_0*"
                 "(omega_Si*(1-2*SOC)+log(SOC/(1-SOC)))+r*u_el)"
                 "*test(u3)"
                 "-k_c*(r*u2r/c_max_Si*test(u3r))");
```

If this is still too long, first split the chemical part into a variable:

```java
model.component("comp1").variable("var2")
     .set("mu_chem", "c_max_Si*R_const*T_0*"
                     "(omega_Si*(1-2*SOC)+log(SOC/(1-SOC)))",
          "chemical contribution to the potential");
model.component("comp1").variable("var2")
     .set("grad_coeff", "k_c/c_max_Si", "gradient-energy coefficient");
```

Then use:

```java
.set("weak", "r*u3*test(u3)"
            "-(r*mu_chem+r*u_el)*test(u3)"
            "-grad_coeff*(r*u2r*test(u3r))");
```

Never hide a stress measure, a modulus derivative, and a boundary value in the
same expression. Name them separately.

## 8. Boundary-condition style

Create a named feature for every physical boundary.

```java
model.component("comp1").physics("w")
     .create("dir1", "DirichletBoundary", 0);
model.component("comp1").physics("w")
     .feature("dir1").selection().set(2);
model.component("comp1").physics("w")
     .feature("dir1").set("r", "c_boundary");
```

Before submission, record:

- boundary entity number and geometry dimension;
- the dependent variable constrained;
- whether the condition applies to the evolution row or the potential row;
- whether a natural boundary is additionally active;
- whether the boundary supplies or removes the conserved quantity.

A named condition such as `c=c_boundary` is not enough. Its weak-form row and
reaction must be verified.

## 9. Initial-condition style

Use `model.init()` when the normal `Initial Values` feature does not persist
the intended fields.

```java
model.init().create("explicit_initial_fields");
model.init("explicit_initial_fields").selection().named("sel_domain");
model.init("explicit_initial_fields").set("c1.u2", "c0");
model.init("explicit_initial_fields").set("c1.u3",
     "log(c0/(1-c0))+omega_Si*(1-2*c0)");
```

For every initial field, state its physical meaning. If a field has a
nonuniform seed, show its profile and verify it lies in the physical range.

## 10. Mesh and discretization

```java
model.component("comp1").mesh("mesh1").create("size1", "Size");
model.component("comp1").mesh("mesh1").feature("size1").set("custom", "on");
model.component("comp1").mesh("mesh1").feature("size1")
     .set("hmax", "0.5[nm]");
```

Record:

- element order for each dependent variable;
- continuous versus discontinuous shape functions;
- Gauss-point integration order;
- whether the mesh resolves the phase interface;
- which quantities are exported at nodes and which at Gauss points.

Do not substitute nodal interpolation for raw Gauss-point constitutive output
when evaluating plastic or interface-sensitive stress.

## 11. Parametric Sweep and study variation

Parameter changes are not separate model builds and must never be represented by
one MPH per parameter value. Add a COMSOL `Study > Parametric Sweep` step, list the
parameter names and values or ranges there, and solve all combinations inside the
same MPH. A parameter-sweep output must include a table with:

| Source symbol | COMSOL parameter name | Values or range | Sweep study |
|---|---|---|---|
| `L` | `L` | `5[mm]`, `10[mm]`, `15[mm]` | `std_sweep` |

Do not create `model_L1.mph`, `model_L2.mph`, or equivalent copies unless the
user explicitly requests separate models and the R2 conflict is recorded.

## 11. Study and solver style

Build-only Java should stop after `model.save`.

```java
model.study().create("std1");
model.study("std1").create("time", "Transient");
model.study("std1").feature("time").set("tlist", "range(0,delta_t,22050[s])");
model.save("Model_built.mph");
```

Do not call `runNoGen()` in a source whose contract is build-only unless the
workflow explicitly requires it.

Record and inspect:

- `tlist` and endpoint;
- geometric nonlinearity setting;
- BDF order;
- `rtol`, `atol`, and field scaling;
- maximum and initial time steps;
- strict output-time behavior;
- whether the actual final accepted time matches the requested endpoint.

A successful solve is not acceptance. Check residuals, conservation, field
bounds, constitutive admissibility, and expected output files.

## 12. Result and export style

Create fixed result expressions rather than relying on GUI state.

Use explicit names:

```text
concentration_profile
chemical_potential_profile
radial_stress
hoop_stress
axial_stress
equivalent_stress
plastic_strain
```

For paper comparisons, define the normalization in the export script:

```text
sigma_r / E_Si
sigma_theta / E_Si
sigma_e = |sigma_r - sigma_theta| / E_Si
```

If the paper's effective stress is `|sigma_r-sigma_theta|`, do not replace it
silently with the three-dimensional von Mises stress. Export both if both are
useful.

## 13. Audit checklist

Before declaring a model ready:

1. Parameters have names, units, and source references.
2. Every constitutive intermediate has a named variable.
3. Weak forms can be decomposed into named physical terms.
4. Native physics features are verified against their stress and strain
   definitions.
5. Boundaries have explicit selections and row assignments.
6. Initial fields are physically admissible and persisted.
7. The mesh and integration order are recorded.
8. Build-only and solve-only jobs are separated.
9. The solved log reaches the requested endpoint.
10. Raw Gauss-point exports are preserved without smoothing.
11. A paper figure is not treated as reproduced until the requested axes,
    normalization, time points, and quantitative metrics are checked.

## 14. Canonical Java skeleton

```java
public final class PaperModel {
  private static Model m;

  private static void par(String name, String value) {
    m.param().set(name, value);
  }

  private static void var(String group, String name, String expression,
                          String description) {
    m.component("comp1").variable(group).set(name, expression, description);
  }

  private static void field(String name, String init, boolean local) {
    // create dependent field
  }

  private static void weak(String tag, String expression) {
    // create WeakContribution or WeakFormPDE residual
  }

  public static Model run() throws Exception {
    m = ModelUtil.create("PaperModel");

    // 1. parameters
    par("A", "70[nm]");
    par("D", "2e-17[m^2/s]");

    // 2. geometry
    // 3. selections
    // 4. variable groups: transport, kinematics, constitutive
    // 5. native physics
    // 6. boundary conditions
    // 7. initial conditions
    // 8. mesh
    // 9. study and solver
    // 10. add Study > Parametric Sweep for every parameter variation
    // 11. keep all parameter combinations in one MPH
    // 12. save one unsolved or sweep-bearing model
    m.save("PaperModel_built.mph");
    return m;
  }

  public static void main(String[] args) throws Exception {
    run();
  }
}
```

The skeleton is intentionally ordered. Preserve the order unless a specific
COMSOL API dependency requires a local change; document that change.

## 15. Anti-patterns

- One equation containing every material law, derivative, and boundary value.
- Repeating numeric constants in multiple weak expressions.
- Hiding the stress measure behind an unlabeled variable name.
- Mixing Cauchy, Piola, and Kirchhoff stress without explicit conversion.
- Setting native `Et` without checking whether it is tangent or hardening
  modulus.
- Calling `runNoGen()` inside a build-only source.
- Reading a solved MPH and recomputing fields instead of exporting them.
- Plotting smoothed nodal values and calling them raw constitutive output.
- Treating a successful build, a completed solver, or a visually similar curve
  as paper reproduction.

## Readability invariant

The important pattern is independent of any particular paper or local file:

```text
parameters
-> named field variables
-> named transport coefficients
-> named mechanics/constitutive quantities
-> native physics features
-> short weak-form expressions
-> boundary and initial values
-> study/solver settings
-> exported diagnostics
```

A model is portable only when those relationships remain visible inside the
target Java source after the external example is removed.
