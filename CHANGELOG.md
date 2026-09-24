# Changelog

All notable changes to PaperSim are recorded here.

## [0.2.0] - 2026-09-24

### Added

- Canonical Case-directory workflow and case naming rules.
- Pydantic v2 Case, Profile, IR, Audit, and Approval contracts.
- PDF-backed deterministic IR auditing.
- Build-only and solve-only COMSOL Java generation.
- COMSOL MPH readback and implementation audit.
- Numerical acceptance and scoped assessment framework.
- Offline HTML report generation.
- Per-feature unit, contract, negative, and end-to-end tests.
- Case/profile migration for canonical names.

### Changed

- Case directories replace the flat object workspace as the supported workflow.
- Profile names follow lowercase `surname + year + _topic`.
- COMSOL solves run declared Study Parametric Sweeps instead of bypassing them with `runAll()`.
