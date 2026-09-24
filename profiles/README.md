# Deterministic extraction profiles

PaperSim's `--profile auto` mode is independent of LLMs and agents. It reads the
PDF, computes a title/abstract keyword score against every registered template,
and selects the template with the highest score above its minimum threshold.
If no template matches, extraction fails closed instead of inventing a physics
mapping.

Each profile contains:

- numbered equation regions and normalized LaTeX;
- equation classification;
- source symbols and COMSOL names;
- values, units, evidence page/quote, and status;
- parameter relations;
- dimensional checks;
- COMSOL Variables, PDEs, Parametric Sweep, and single-MPH specification.

To add a new deterministic model family:

1. Copy `huang2013_lithiation.json` to `<paper_or_family>.json`.
2. Replace equations, parameters, units, relations, and Java model structure.
3. Add title/abstract keywords and a minimum score to `TEMPLATES` in
   `src/papersim/auto.py`.
4. Run `pytest`/`unittest` and require independent extraction review to pass.
5. Verify the generated Java with `comsol compile` and a build-only batch run.

The profile is a deterministic physics/translation contract, not an LLM prompt.
