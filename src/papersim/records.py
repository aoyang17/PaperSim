from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class Primitive:
    """A typed view over one canonical JSON object."""

    id: str
    path: Path
    data: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return dict(self.data)

    def __getattr__(self, name: str) -> Any:
        data = object.__getattribute__(self, "data")
        if name in data:
            return data[name]
        raise AttributeError(name)


@dataclass(frozen=True)
class Case(Primitive):
    pass


@dataclass(frozen=True)
class Model(Primitive):
    pass


@dataclass(frozen=True)
class Run(Primitive):
    pass


@dataclass(frozen=True)
class Compare(Primitive):
    pass


@dataclass(frozen=True)
class Assess(Primitive):
    pass
