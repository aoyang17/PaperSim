from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest

from papersim import Engine
from papersim.case_contracts import SolverSpec
from papersim.comsol import ComsolBackend
from papersim.contracts import AgentAdapter, AgentResult, AgentTask, ContractError, RemoteResult, TranslationGap
from papersim.run import FakeSolver
from papersim.store import StoreError, Workspace, validate_object

EXAMPLE_DIR = ROOT / "examples" / "mvp" / "yeesuan_comsol"
sys.path.insert(0, str(EXAMPLE_DIR))

from adapter import build_backend
from yeesuan_executor import YeesuanConfig, YeesuanExecutor


MODEL_SECTIONS = (
    "Scope",
    "Variables",
    "Governing Equations",
    "Constitutive Equations",
    "Parameters",
    "Initial Conditions",
    "Boundary Conditions",
    "Assumptions",
    "Solver Mapping",
    "Outputs",
    "Evidence",
    "Open Gaps",
    "Change Log",
)


def markdown(extra: str = "") -> str:
    return "# Model\n" + "".join(f"## {section}\n\n{extra or section}\n" for section in MODEL_SECTIONS)


def model_spec(value: float = 2.0, backend: str = "fake") -> dict:
    return {
        "scope": "synthetic golden-chain contract test",
        "variables": [
            {"id": "p", "symbol": "p", "meaning": "phase field", "source": "paper", "evidence": ["M1"]}
        ],
        "governing_equations": [
            {"id": "eq1", "expression": "dp/dt=0", "source": "paper", "evidence": ["M1"]}
        ],
        "constitutive_equations": [
            {"id": "c1", "expression": "f=p(1-p)", "source": "paper", "evidence": ["M1"]}
        ],
        "parameters": [
            {
                "id": "simulated_value",
                "name": "simulated value",
                "value": value,
                "units": "1",
                "source": "extracted",
                "evidence": ["P1"],
            }
        ],
        "initial_conditions": [
            {"id": "ic1", "variable": "p", "value": 0.0, "source": "paper", "evidence": ["M1"]}
        ],
        "boundary_conditions": [
            {"id": "bc1", "variable": "p", "condition": "zero flux", "source": "paper", "evidence": ["M1"]}
        ],
        "assumptions": [
            {"id": "a1", "statement": "test fixture", "source": "assumption", "evidence": []}
        ],
        "solver": {"backend": backend, "version": "1.0"},
        "outputs": [
            {"id": "simulation.value", "name": "simulated value", "units": "1", "metric": "simulation.value"}
        ],
        "acceptance": [
            {
                "id": "acceptance-1",
                "metric": "simulation.value",
                "operator": "relative_error_le",
                "expected": 2.0,
                "tolerance": 0.01,
                "required": True,
            }
        ],
        "evidence": ["M1"],
        "open_gaps": [],
        "assessment": {"verdict_on_pass": "qualified", "verdict_on_fail": "not_reproduced"},
        "unresolved_questions": ["verify numerical convergence"],
    }


class DummyModelAgent(AgentAdapter):
    adapter_name = "dummy-model"
    adapter_version = "1.0"

    def capabilities(self) -> set[str]:
        return {"model"}

    def run(self, task: AgentTask) -> AgentResult:
        if task.kind != "model":
            return AgentResult(kind=task.kind, status="error", message="unsupported")
        return AgentResult(
            kind="model",
            outputs={"markdown": markdown(), "spec": model_spec()},
        )


class DummyWorkflowAgent(AgentAdapter):
    adapter_name = "dummy-workflow"
    adapter_version = "1.0"

    def capabilities(self) -> set[str]:
        return {"model", "compare", "assess"}

    def run(self, task: AgentTask) -> AgentResult:
        if task.kind == "model":
            return AgentResult(kind="model", outputs={"markdown": markdown(), "spec": model_spec()})
        if task.kind == "compare":
            return AgentResult(
                kind="compare",
                outputs={
                    "observed": {"obs-1": 2.0},
                    "simulated": {"obs-1": 2.0},
                    "errors": {"obs-1": {"absolute": 0.0, "relative": 0.0}},
                    "metrics": {"simulation.value": 2.0},
                    "mismatches": [],
                    "uncertainty": [{"id": "u1", "kind": "declared", "value": 0.0}],
                    "evidence": ["obs-1"],
                    "interpretation": "agent comparison",
                },
            )
        if task.kind == "assess":
            return AgentResult(
                kind="assess",
                outputs={
                    "verdict": "supported",
                    "confidence": "high",
                    "scope": "agent scope",
                    "findings": [{"id": "f1", "passed": True}],
                    "unresolved_questions": [],
                },
            )
        return AgentResult(kind=task.kind, status="error", message="unsupported")


class DummyRemoteExecutor:
    def __init__(self, description: dict | None = None) -> None:
        self.calls: list[tuple] = []
        self.description = description or {"executor": "dummy", "solver_version": "test"}

    def run(self, command: str, *, timeout: int = 60) -> RemoteResult:
        self.calls.append(("run", command, timeout))
        return RemoteResult(command=command, returncode=0, output="")

    def upload(self, local_path, remote_path: str, *, timeout: int = 1800) -> RemoteResult:
        self.calls.append(("upload", str(local_path), remote_path, timeout))
        return RemoteResult(command="scp", returncode=0, output="")

    def download(self, remote_path: str, local_path, *, timeout: int = 1800) -> RemoteResult:
        self.calls.append(("download", remote_path, str(local_path), timeout))
        return RemoteResult(command="scp", returncode=0, output="")

    def describe(self) -> dict:
        return dict(self.description)


class PapersimContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.workspace = root / "workspace"
        self.paper_root = root / "papers"
        self.paper_root.mkdir()
        self.paper = self.paper_root / "source.pdf"
        self.paper.write_bytes(b"%PDF-1.4\nfixture\n")
        self.engine = Engine.open(
            self.workspace,
            paper_root=self.paper_root,
            solvers={"fake": FakeSolver()},
            host_name="contract-test",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def draft(self, value: float = 2.0, backend: str = "fake", extra: str = "") -> Path:
        path = Path(tempfile.mkdtemp(prefix="papersim-draft-", dir=self.temp.name))
        (path / "model.md").write_text(markdown(extra), encoding="utf-8")
        (path / "model.spec.json").write_text(json.dumps(model_spec(value, backend)), encoding="utf-8")
        return path

    def case(self):
        return self.engine.case(
            self.paper,
            case_id="synthetic-paper",
            metadata={"title": "Synthetic paper", "authors": ["Tester"], "year": 2026},
            observations=[
                {
                    "id": "obs-1",
                    "quantity": "simulated value",
                    "value": 2.0,
                    "units": "1",
                    "source": "paper",
                    "metric": "simulation.value",
                }
            ],
        )

    def build_chain(self):
        case = self.case()
        model = self.engine.model(case.id, source=self.draft())
        run = self.engine.run(model.id, backend="fake", solver=FakeSolver(metrics={"simulation.value": 2.0}))
        compare = self.engine.compare(run.id, case=case.id)
        assess = self.engine.assess(case.id)
        return case, model, run, compare, assess

    def test_each_object_contract_has_a_positive_and_negative_case(self) -> None:
        case, model, run, compare, assess = self.build_chain()
        positive = {
            "case": case.data,
            "model": model.data,
            "run": run.data,
            "compare": compare.data,
            "assess": assess.data,
        }
        for kind, payload in positive.items():
            validate_object(kind, payload)
        negative = {
            "case": {key: value for key, value in case.data.items() if key != "producer"},
            "model": {**model.data, "model_md": None},
            "run": {**run.data, "status": "not-a-status"},
            "compare": {key: value for key, value in compare.data.items() if key != "errors"},
            "assess": {**assess.data, "verdict": "published"},
        }
        for kind, payload in negative.items():
            with self.subTest(kind=kind):
                with self.assertRaises(StoreError):
                    validate_object(kind, payload)

    def test_source_topology_is_flat_and_contains_only_adr_modules(self) -> None:
        package = ROOT / "src" / "papersim"
        expected = {
            "__init__.py",
            "engine.py",
            "records.py",
            "store.py",
            "model.py",
            "run.py",
            "compare.py",
            "assess.py",
            "contracts.py",
            "comsol.py",
            "cli.py",
            "documents.py",
            "units.py",
            "extraction.py",
            "review.py",
            "java.py",
            "auto.py",
            "case_contracts.py",
            "case_store.py",
            "case_audit.py",
            "case_java.py",
            "case_implementation.py",
            "case_numeric.py",
            "case_report.py",
            "case_workflow.py",
            "case_migration.py",
            "schemas.py",
            "case_mph.py",
        }
        self.assertEqual({item.name for item in package.iterdir() if item.is_file() and item.suffix == ".py"}, expected)
        self.assertFalse((package / "adapters").exists())

    def test_workspace_can_carry_the_independent_paper_corpus(self) -> None:
        root = Path(self.temp.name) / "workspace-with-paper"
        (root / "paper" / "original").mkdir(parents=True)
        paper = root / "paper" / "original" / "P1__paper.pdf"
        paper.write_bytes(b"paper")
        engine = Engine.open(root)
        self.assertEqual(engine.paper_root, (root / "paper" / "original").resolve())
        self.assertEqual({item.name for item in root.iterdir()}, {"objects", "artifacts", "tmp", "paper"})

    def test_workspace_contains_only_three_flat_directories(self) -> None:
        self.assertEqual({item.name for item in self.workspace.iterdir()}, {"objects", "artifacts", "tmp"})
        self.assertTrue((self.workspace / "objects").is_dir())
        self.assertTrue((self.workspace / "artifacts").is_dir())
        self.assertTrue((self.workspace / "tmp").is_dir())

    def test_full_golden_chain_with_fake_solver(self) -> None:
        case = self.case()
        first = self.engine.model(case.id, source=self.draft(2.0))
        baseline = self.engine.run(first.id, backend="fake")
        first_compare = self.engine.compare(baseline.id, case=case.id)
        self.assertEqual(first_compare.data["observed"]["obs-1"], 2.0)
        self.assertEqual(first_compare.data["simulated"]["obs-1"], 0.0)
        self.assertTrue(first_compare.data["errors"]["obs-1"]["relative"] == 1.0)
        self.assertEqual(len(first_compare.data["mismatches"]), 1)

        second = self.engine.model(
            case.id,
            source=self.draft(2.1, extra="revised"),
            parent=first.id,
            compare=first_compare.id,
            change_reason="change simulated value after diagnosis",
        )
        second_run = self.engine.run(second.id, backend="fake", solver=FakeSolver(metrics={"simulation.value": 2.01}))
        second_compare = self.engine.compare(second_run.id, case=case.id)
        self.assertEqual(len(second_compare.data["mismatches"]), 0)
        assess = self.engine.assess(case.id)
        self.assertEqual(assess.data["verdict"], "qualified")
        self.assertTrue(assess.data["scope"])
        self.assertTrue(assess.data["unresolved_questions"])
        self.assertEqual(self.engine.handshake()["counts"], {"case": 1, "model": 2, "run": 2, "compare": 2, "assess": 1})

        # All canonical object files are flat and immutable.
        self.assertEqual(
            sorted(path.name for path in (self.workspace / "objects").iterdir()),
            [
                "assess_a0001.json",
                "case_synthetic-paper.json",
                "compare_c0001.json",
                "compare_c0002.json",
                "model_m0001.json",
                "model_m0002.json",
                "run_r0001.json",
                "run_r0002.json",
            ],
        )
        self.assertFalse(any(path.is_dir() for path in (self.workspace / "artifacts").rglob("*")))

    def test_invalid_model_schema_is_rejected_before_canonical_write(self) -> None:
        case = self.case()
        draft = self.draft()
        spec = model_spec()
        del spec["variables"]
        (draft / "model.spec.json").write_text(json.dumps(spec), encoding="utf-8")
        with self.assertRaises(ContractError):
            self.engine.model(case.id, source=draft)
        self.assertFalse((self.workspace / "objects" / "model_m0001.json").exists())

    def test_model_markdown_requires_standard_sections(self) -> None:
        case = self.case()
        draft = self.draft()
        (draft / "model.md").write_text("# Model\n## Scope\nonly one section\n", encoding="utf-8")
        with self.assertRaises(ContractError):
            self.engine.model(case.id, source=draft)

    def test_duplicate_paper_hash_is_not_registered_twice(self) -> None:
        first = self.engine.paper_repo.register(self.paper, paper_id="P1", metadata={"title": "One"})
        second = self.engine.paper_repo.register(self.paper, paper_id="P2", metadata={"title": "Two"})
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(len(self.engine.paper_repo.entries()), 1)

    def test_agent_adapter_can_replace_compare_and_assess_tasks(self) -> None:
        case = self.case()
        agent = DummyWorkflowAgent()
        model = self.engine.model(case.id, agent=agent)
        run = self.engine.run(model.id, backend="fake", solver=FakeSolver(metrics={"simulation.value": 2.0}))
        compare = self.engine.compare(run.id, case=case.id, agent=agent)
        self.assertEqual(compare.data["interpretation"], "agent comparison")
        assess = self.engine.assess(case.id, agent=agent)
        self.assertEqual(assess.data["verdict"], "supported")
        self.assertEqual(assess.data["scope"], "agent scope")

    def test_compare_and_assess_gates_fail_closed(self) -> None:
        case = self.case()
        model = self.engine.model(case.id, source=self.draft())
        with self.assertRaises(ContractError):
            self.engine.assess(case.id)
        failed = FakeSolver(fail=True)
        with self.assertRaises(ContractError):
            self.engine.run(model.id, backend="failed", solver=failed)
        failed_id = self.engine.workspace.read_object("case", case.id)["run_ids"][0]
        self.assertEqual(self.engine.workspace.read_object("run", failed_id)["status"], "failed")
        self.assertFalse(self.engine.workspace.read_object("run", failed_id)["baseline"])

    def test_changed_markdown_without_regenerated_spec_is_marked_stale_and_cannot_run(self) -> None:
        case = self.case()
        first = self.engine.model(case.id, source=self.draft())
        stale = self.engine.model(
            case.id,
            source=self.draft(extra="markdown changed without spec regeneration"),
            parent=first.id,
            change_reason="documentation clarification",
        )
        self.assertEqual(stale.data["spec_status"], "stale")
        with self.assertRaises(ContractError):
            self.engine.run(stale.id, backend="fake")

    def test_agent_adapter_can_substitute_for_model_task(self) -> None:
        case = self.case()
        agent = DummyModelAgent()
        model = self.engine.model(case.id, agent=agent)
        self.assertEqual(model.data["created_by"], "dummy-model")
        spec = self.engine._model_spec(model.data)
        self.assertEqual(spec["scope"], "synthetic golden-chain contract test")

    def test_schema_rejects_missing_uniform_envelope_field(self) -> None:
        data = self.engine.case(self.paper, metadata={"title": "One"}, observations=[]).data
        broken = dict(data)
        broken.pop("producer")
        with self.assertRaises(StoreError):
            validate_object("case", broken)

    def test_nested_workspace_directory_is_rejected(self) -> None:
        (self.workspace / "objects" / "nested").mkdir()
        with self.assertRaises(StoreError):
            Workspace(self.workspace).validate_all()

    def test_yeesuan_mvp_identity_file_enables_legacy_publickey_auth(self) -> None:
        root = Path(self.temp.name)
        identity = root / "remote_key"
        identity.write_text("test-key", encoding="utf-8")
        config = root / "comsol-key.json"
        config.write_text(
            json.dumps(
                {
                    "ssh": {
                        "host": "example",
                        "port": 22,
                        "user": "u",
                        "instance_selection": "1",
                        "identity_file": str(identity),
                    },
                    "remote": {"environment_script": "~/env.sh"},
                }
            ),
            encoding="utf-8",
        )
        executor = YeesuanExecutor(YeesuanConfig.load(config), config)
        options = executor._auth_options()
        self.assertEqual(options[:2], ["-i", str(identity)])
        self.assertIn("PreferredAuthentications=publickey,keyboard-interactive", options)

    def test_yeesuan_mvp_direct_instance_identity_uses_batch_publickey_auth(self) -> None:
        root = Path(self.temp.name)
        identity = root / "remote_key"
        identity.write_text("test-key", encoding="utf-8")
        config = root / "comsol-direct.json"
        config.write_text(
            json.dumps(
                {
                    "ssh": {
                        "host": "example",
                        "port": 22,
                        "user": "u",
                        "instance_selection": "1",
                        "instance_id": "12345",
                        "identity_file": str(identity),
                    },
                    "remote": {"environment_script": "~/env.sh"},
                }
            ),
            encoding="utf-8",
        )
        executor = YeesuanExecutor(YeesuanConfig.load(config))
        options = executor._auth_options()
        self.assertEqual(executor._login_user(), "u::12345")
        self.assertIn("BatchMode=yes", options)
        self.assertIn("KbdInteractiveAuthentication=no", options)
        self.assertIn("PreferredAuthentications=publickey", options)

        completed = SimpleNamespace(returncode=0, stdout="remote-host\n", stderr="")
        with patch("yeesuan_executor.subprocess.run", return_value=completed) as run:
            result = executor.run("hostname", timeout=5)
        self.assertTrue(result.ok)
        self.assertEqual(result.output, "remote-host")
        command = run.call_args.args[0]
        self.assertEqual(command[0], "ssh")
        self.assertIn("u::12345@example", command)
        self.assertTrue(command[-1].endswith("&& hostname"))

        solver = build_backend(config=config)
        self.assertIsInstance(solver, ComsolBackend)
        self.assertEqual(solver.remote_root, "~/papersim_cases")
        self.assertEqual(solver.solver_version, "6.4")

    def test_comsol_backend_requires_a_translatable_model(self) -> None:
        case = self.case()
        model = self.engine.model(case.id, source=self.draft(backend="comsol"))
        backend = ComsolBackend(DummyRemoteExecutor(), remote_root="/tmp/remote", suite="full")
        with self.assertRaises(TranslationGap):
            backend.validate(model)

    def test_engine_requires_external_solver_injection(self) -> None:
        case = self.case()
        model = self.engine.model(case.id, source=self.draft(backend="comsol"))
        with self.assertRaisesRegex(ContractError, "no solver registered"):
            self.engine.run(model.id, backend="comsol")

    def test_case_contract_accepts_user_defined_solver_backend_name(self) -> None:
        spec = SolverSpec(backend="custom-external", version="1.0", settings={})
        self.assertEqual(spec.backend, "custom-external")


if __name__ == "__main__":
    unittest.main()


@pytest.mark.pdf
class ExtractionTests(unittest.TestCase):
    def test_unit_validator_accepts_compatible_units_and_rejects_mismatch(self) -> None:
        from papersim.units import UnitValidator

        validator = UnitValidator()
        self.assertTrue(validator.compatible("Pa/m", "Pa/m"))
        self.assertFalse(validator.compatible("Pa", "1/s"))
        self.assertAlmostEqual(validator.convert(1.0, "GPa", "MPa"), 1000.0)
        self.assertTrue(validator.validate_parameter(0.001, "1/s")["passed"])
        self.assertFalse(validator.validate_parameter(0.001, "not-a-unit")["passed"])

    def test_huang_pdf_auto_profile_resolution(self) -> None:
        configured = os.environ.get("PAPERSIM_HUANG_PDF")
        pdf = Path(configured) if configured else Path("/nonexistent")
        if not pdf.is_file():
            self.skipTest("Huang 2013 PDF fixture is unavailable")
        from papersim.auto import resolve_auto_profile

        selection = resolve_auto_profile(pdf)
        self.assertEqual(selection.template_name, "huang2013_lithiation_stress")
        self.assertGreaterEqual(selection.score, 0.6)
        self.assertTrue(selection.profile_path.is_file())

    def test_chen_pdf_auto_extraction_review_and_single_java(self) -> None:
        configured = os.environ.get("PAPERSIM_CHEN_PDF")
        pdf = Path(configured) if configured else Path("/nonexistent")
        if not pdf.is_file():
            self.skipTest("Chen 2014 PDF fixture is unavailable")
        from papersim.auto import resolve_auto_profile
        from papersim.extraction import extract_paper
        from papersim.java import generate_java
        from papersim.review import review_extraction

        selection = resolve_auto_profile(pdf)
        self.assertEqual(selection.template_name, "chen2014_phase_field_elastoplastic")
        with tempfile.TemporaryDirectory() as temporary:
            bundle = extract_paper(pdf, selection.profile_path, extraction_dir=Path(temporary) / "regions")
            self.assertGreaterEqual(len(bundle.equations), 30)
            self.assertGreaterEqual(len(bundle.parameters), 15)
            review = review_extraction(bundle)
            self.assertTrue(review.passed, review.as_dict())
            java_path = generate_java(bundle, Path(temporary) / "Chen2014PaperConstitutive.java")
            text = java_path.read_text(encoding="utf-8")
            self.assertIn("Chen2014PaperConstitutive_built.mph", text)
            self.assertIn("1. equation_classification", text)
            self.assertIn("8. self_check", text)
            self.assertEqual(text.count(".mph"), 2)

    def test_huang_pdf_extraction_review_and_single_java(self) -> None:
        configured = os.environ.get("PAPERSIM_HUANG_PDF")
        pdf = Path(configured) if configured else Path("/nonexistent")
        profile = ROOT / "profiles" / "huang2013_lithiation.json"
        if not pdf.is_file() or not profile.is_file():
            self.skipTest("Huang 2013 PDF/profile fixture is unavailable")
        from papersim.documents import PdfDocument
        from papersim.extraction import extract_paper
        from papersim.java import generate_java
        from papersim.review import review_extraction

        document = PdfDocument(pdf)
        try:
            equations = document.equation_regions()
        finally:
            document.close()
        numbers = {item.number for item in equations}
        self.assertTrue(set(range(1, 20)).issubset(numbers))
        with tempfile.TemporaryDirectory() as temporary:
            bundle = extract_paper(pdf, profile, extraction_dir=Path(temporary) / "regions")
            self.assertEqual(len(bundle.equations), 19)
            self.assertGreaterEqual(len(bundle.parameters), 10)
            self.assertTrue(all(check["passed"] for check in bundle.unit_equation_checks.values()))
            review = review_extraction(bundle)
            self.assertTrue(review.passed, review.as_dict())
            java_path = generate_java(bundle, Path(temporary) / "Huang2013PaperConstitutive.java")
            text = java_path.read_text(encoding="utf-8")
            self.assertIn("1. equation_classification", text)
            self.assertIn("6. parametric_sweep", text)
            self.assertIn("7. report_nomenclature", text)
            self.assertIn("8. self_check", text)
            self.assertEqual(text.count(".mph"), 1)
            self.assertNotIn("runNoGen", text)
