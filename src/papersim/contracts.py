from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable


class PaperSimError(RuntimeError):
    """Base class for fail-closed PaperSim errors."""


class StoreError(PaperSimError):
    """Raised when canonical state or an artifact is invalid."""


class ContractError(PaperSimError):
    """Raised when an adapter violates a PaperSim contract."""


class UnsupportedModel(ContractError):
    """Raised when a solver cannot translate a model."""


class TranslationGap(ContractError):
    """Raised when a required model translation is not represented."""


@dataclass(frozen=True)
class Producer:
    papersim_version: str
    schema_version: str
    adapter_name: str
    adapter_version: str
    host_name: str

    def as_dict(self) -> dict[str, str]:
        return {
            "papersim_version": self.papersim_version,
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "adapter_version": self.adapter_version,
            "host_name": self.host_name,
        }


@dataclass(frozen=True)
class ArtifactRef:
    """A flat artifact addressed by hash, with a logical name for humans."""

    name: str
    sha256: str
    size: int
    media_type: str = "application/octet-stream"
    path: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sha256": self.sha256,
            "size": self.size,
            "media_type": self.media_type,
            "path": self.path,
        }


@dataclass(frozen=True)
class RemoteResult:
    """Result returned by an externally supplied solver executor."""

    command: str
    returncode: int
    output: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "returncode": self.returncode, "output": self.output}


@dataclass(frozen=True)
class AgentTask:
    """Typed task submitted by Engine to an injected AgentAdapter."""

    kind: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in {"case", "model", "compare", "assess"}:
            raise ContractError(f"unsupported agent task kind: {self.kind}")


@dataclass(frozen=True)
class AgentResult:
    """Agent output. Agents submit drafts; Engine owns canonical writes."""

    kind: str
    outputs: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[ArtifactRef, ...] = ()
    status: str = "ok"
    message: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"ok", "error"}:
            raise ContractError(f"unsupported agent result status: {self.status}")


@runtime_checkable
class AgentAdapter(Protocol):
    def capabilities(self) -> set[str]:
        ...

    def run(self, task: AgentTask) -> AgentResult:
        ...


@runtime_checkable
class SolverBackend(Protocol):
    def validate(self, model: Any) -> None:
        ...

    def build(self, model: Any, workdir: Any) -> Mapping[str, Any]:
        ...

    def submit(self, model: Any, run_id: str, workdir: Any) -> Mapping[str, Any]:
        ...

    def status(self, run_id: str) -> Mapping[str, Any]:
        ...

    def collect(self, run_id: str, workdir: Any) -> Mapping[str, Any]:
        ...


@runtime_checkable
class RemoteExecutor(Protocol):
    """User-supplied transport for a remote solver.

    PaperSim defines this interface but does not define gateway URLs, instance
    identifiers, credentials, schedulers, or site-specific paths. Users inject
    their own implementation when constructing a solver backend.
    """

    def run(self, command: str, *, timeout: int = 60) -> RemoteResult:
        ...

    def upload(self, local_path: Any, remote_path: str, *, timeout: int = 1800) -> RemoteResult:
        ...

    def download(self, remote_path: str, local_path: Any, *, timeout: int = 1800) -> RemoteResult:
        ...

    def describe(self) -> Mapping[str, Any]:
        """Return non-secret execution metadata recorded with the run."""
        ...
