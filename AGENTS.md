# PaperSim Global Rules

For every PaperSim case that builds, revises, or audits a COMSOL Java model or MPH:

1. Read and follow `skills/comsol-modeling/SKILL.md` before writing Java.
2. Write the parameter, variable, equation, boundary-condition, initial-condition, mesh, solver, and export tables before the Java implementation.
3. Keep every physical quantity and constitutive intermediate as a named COMSOL parameter or variable.
4. Do not hard-code machine-specific paths, credentials, partitions, or remote locations in physics code.
5. Keep build-only Java deterministic and separate from the solve job. Build-only code must stop after saving the unsolved MPH; solve/export is a separate job.
6. Verify persisted feature properties, units, selections, initial values, solver settings, residuals, conservation, field bounds, and requested endpoints before declaring reproduction success.
7. Include the equation-to-feature mapping and the model audit checklist in the final HTML report.
