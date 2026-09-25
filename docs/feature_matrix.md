# PaperSim Feature and Test Matrix

| Feature | Python implementation | Independent test | Failure gate |
|---|---|---|---|
| Case naming | `case_contracts.py` | `tests/features/test_case_naming.py` | rejects non-ASCII, path fragments, missing/extra topic words |
| Case layout | `case_store.py` | `tests/features/test_case_layout.py` | rejects duplicate Case, renamed/tampered paper |
| Profile contract | `case_contracts.py` | `tests/features/test_kobayashi_profile.py` | missing references, invalid units, empty acceptance |
| PDF evidence and IR | `case_audit.py` | `tests/features/test_ir_audit.py`, `test_real_pdf_audit.py` | quote, page, bbox, SHA-256, symbol or unit mismatch |
| Approval | `case_audit.py` | `tests/features/test_ir_audit.py` | unapproved build or stale hash |
| Java generation | `case_java.py` | `tests/features/test_java_generation.py` | inlined constitutive terms, no sweep, build/solve mixed |
| MPH readback | `case_mph.py` | `tests/features/test_mph_readback.py` | malformed MPH, changed expression/unit/feature |
| COMSOL implementation audit | `case_implementation.py` | `tests/features/test_implementation_audit.py` | changed parameter, variable, selection, mesh or solver |
| Numerical audit | `case_numeric.py` | `tests/features/test_numeric_and_report.py` | wrong endpoint, fatal log, failed conservation or bounds |
| HTML report | `case_report.py` | `tests/features/test_numeric_and_report.py` | external resource, missing nomenclature/audit mapping |
| Migration | `case_migration.py` | `tests/features/test_migration.py` | target collision, missing source, hash change |
| End-to-end workflow | `case_workflow.py` | `tests/features/test_case_workflow.py` | any stage bypass or missing artifact |
| External solver injection | `contracts.py`, `comsol.py`, `engine.py` | `tests/test_papersim_contracts.py` | unregistered backend is not auto-constructed; executor methods are mandatory |
| All-parametric export | `profiles/templates/kobayashi1993_dendrite_solve.java` | `tests/features/test_java_generation.py` | export must bind to the stored parametric solution dataset |

## Commands

```bash
PYTHONPATH=src pytest tests/features/test_case_naming.py
PYTHONPATH=src pytest tests/features/test_ir_audit.py
PYTHONPATH=src pytest tests/features/test_java_generation.py
PYTHONPATH=src pytest tests/features/test_case_workflow.py
PYTHONPATH=src pytest -m "not pdf and not comsol"
```
