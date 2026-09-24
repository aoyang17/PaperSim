"""PaperSim: auditable paper model reproduction and reliability assessment."""

from .auto import AutoProfileSelection, resolve_auto_profile
from .case_contracts import (
    AuditRecord,
    CaseManifest,
    IR,
    ProfileModel,
    iteration_name,
    make_case_id,
)
from .case_mph import read_mph_snapshot
from .case_store import CaseLayout, CaseStore
from .case_workflow import CaseWorkflow
from .contracts import AgentAdapter, AgentResult, AgentTask, SolverBackend
from .documents import EvidenceRef, PdfDocument
from .engine import Engine, load_host_profile
from .extraction import ExtractionBundle, extract_paper, load_extraction_profile
from .java import generate_java
from .records import Assess, Case, Compare, Model, Run
from .review import review_extraction
from .schemas import export_schemas
from .store import PAPERSIM_VERSION, SCHEMA_VERSION as _SCHEMA_VERSION
from .units import UnitValidator

__version__ = PAPERSIM_VERSION
SCHEMA_VERSION = _SCHEMA_VERSION

__all__ = [
    "AgentAdapter",
    "AgentResult",
    "AgentTask",
    "AuditRecord",
    "AutoProfileSelection",
    "Assess",
    "Case",
    "CaseLayout",
    "CaseManifest",
    "CaseStore",
    "CaseWorkflow",
    "Compare",
    "Engine",
    "EvidenceRef",
    "ExtractionBundle",
    "IR",
    "Model",
    "PdfDocument",
    "ProfileModel",
    "read_mph_snapshot",
    "Run",
    "SCHEMA_VERSION",
    "SolverBackend",
    "UnitValidator",
    "__version__",
    "export_schemas",
    "extract_paper",
    "generate_java",
    "iteration_name",
    "load_extraction_profile",
    "load_host_profile",
    "make_case_id",
    "resolve_auto_profile",
    "review_extraction",
]
