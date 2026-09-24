"""Read COMSOL MPH archives into a deterministic implementation snapshot."""

from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any, Iterable, Mapping
import zipfile
import xml.etree.ElementTree as ET

from .contracts import ContractError


def _settings_map(node: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in node.get("settings", []) or []:
        if not isinstance(item, Mapping) or "name" not in item:
            continue
        result[str(item["name"])] = item.get("apiValue", item.get("value"))
    return result


def _walk_nodes(node: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(node, Mapping):
        yield node
        for child in node.get("nodes", []) or []:
            yield from _walk_nodes(child)
    elif isinstance(node, list):
        for child in node:
            yield from _walk_nodes(child)


def _component(model: Mapping[str, Any], tag: str = "comp1") -> Mapping[str, Any]:
    for node in model.get("nodes", []) or []:
        if isinstance(node, Mapping) and node.get("tag") == tag:
            return node
    raise ContractError(f"MPH snapshot is missing component {tag}")


def _find_physics(component: Mapping[str, Any], tag: str) -> Mapping[str, Any]:
    for node in component.get("nodes", []) or []:
        if isinstance(node, Mapping) and node.get("tag") == tag and node.get("apiClass") == "Physics":
            return node
    raise ContractError(f"MPH snapshot is missing physics feature {tag}")


def _dependent_variables(physics: Mapping[str, Any]) -> list[str]:
    settings = _settings_map(physics)
    for name, value in settings.items():
        if not name.startswith("u"):
            continue
        if isinstance(value, list) and len(value) >= 2:
            candidate = value[1]
            if isinstance(candidate, list):
                return [str(item) for item in candidate]
            if isinstance(candidate, str):
                return [candidate]
    return []


def _physics_snapshot(physics: Mapping[str, Any]) -> dict[str, Any]:
    settings = _settings_map(physics)
    feature_types = []
    feature_tags = []
    for item in physics.get("nodes", []) or []:
        if not isinstance(item, Mapping):
            continue
        tag = str(item.get("tag") or "")
        label = str(item.get("label") or "")
        feature_tags.append(tag)
        feature_types.append(label)
    dependent_quantity = settings.get("DependentVariableQuantity") or "unknown"
    source_quantity = settings.get("SourceTermQuantity") or "unknown"
    return {
        "type": physics.get("apiType") or physics.get("op") or "unknown",
        "dependent": _dependent_variables(physics),
        "feature_tags": feature_tags,
        "feature_types": feature_types,
        "units": {
            "dependent_unit": "1" if dependent_quantity == "dimensionless" else str(dependent_quantity),
            "source_unit": str(source_quantity),
        },
    }


def _physics_units_from_dmodel(dmodel_xml: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    try:
        root = ET.fromstring(dmodel_xml)
    except ET.ParseError:
        return result
    for physics in root.iter("Physics"):
        tag = str(physics.get("tag") or "")
        props: dict[str, str] = {}
        for prop in physics.iter("PhysicsProp"):
            if prop.get("tag") != "Units":
                continue
            for parameter in prop.iter("param"):
                name = str(parameter.get("param") or "")
                value = str(parameter.get("value") or "")
                if ",'" in value and value.endswith("'"):
                    value = value.rsplit(",'", 1)[1][:-1]
                props[name] = value
        if tag and props:
            dependent = props.get("CustomDependentVariableUnit", props.get("DependentVariableQuantity", ""))
            source = props.get("CustomSourceTermUnit", props.get("SourceTermQuantity", ""))
            result[tag] = {"dependent_unit": dependent or "unknown", "source_unit": source or "unknown"}
    return result


def _parameter_snapshot(model: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for group in _walk_nodes(model):
        if group.get("apiClass") != "ModelParamGroup":
            continue
        for item in group.get("settings", []) or []:
            if isinstance(item, Mapping) and item.get("name"):
                result[str(item["name"])] = str(item.get("value", ""))
    return result


def _variables_snapshot(component: Mapping[str, Any]) -> dict[str, dict[str, dict[str, str]]]:
    result: dict[str, dict[str, dict[str, str]]] = {}
    for group in _walk_nodes(component):
        if group.get("apiClass") != "Expr":
            continue
        entries: dict[str, dict[str, str]] = {}
        for item in group.get("settings", []) or []:
            if isinstance(item, Mapping) and item.get("name"):
                entries[str(item["name"])] = {
                    "expression": str(item.get("value", "")),
                    "description": str(item.get("description", "")),
                }
        result[str(group.get("tag"))] = entries
    return result


def _mesh_snapshot(component: Mapping[str, Any]) -> dict[str, Any]:
    for node in _walk_nodes(component):
        if node.get("apiClass") != "MeshSequence":
            continue
        child_labels = [str(item.get("label") or "") for item in node.get("nodes", []) or [] if isinstance(item, Mapping)]
        mesh_type = "Mapped" if any("mapped" in label.lower() for label in child_labels) else "unknown"
        return {"tag": node.get("tag"), "type": mesh_type, "features": child_labels}
    return {"type": "missing"}


def _study_and_solver_snapshot(model: Mapping[str, Any], dmodel_xml: str) -> tuple[dict[str, Any], dict[str, Any]]:
    pname_tag = re.search(r'<propertyValue[^>]*name="p:pname"[^>]*>', dmodel_xml)
    plist_tag = re.search(r'<propertyValue[^>]*name="p:plistarr"[^>]*>', dmodel_xml)
    pname_values = re.findall(r"'([^']*)'", pname_tag.group(0)) if pname_tag else []
    plist_values = re.findall(r"'([^']*)'", plist_tag.group(0)) if plist_tag else []
    values: list[Any] = []
    if plist_values:
        values = [float(item) for item in plist_values[-1].replace("\\,", ",").split(",")]
    study = {
        "parametric": {
            "parameter": pname_values[-1] if pname_values else "",
            "values": values,
        }
    }
    solver = {"method": "", "rtol": None, "tfinal": None, "maxorder": None, "maxstep": None}
    for node in _walk_nodes(model):
        settings = _settings_map(node)
        if node.get("tag") == "t1" and node.get("type") == "Time_dependent_solver":
            solver.update(
                {
                    "method": str(settings.get("timemethod") or "").lower(),
                    "rtol": settings.get("rtol"),
                    "maxorder": settings.get("maxorder"),
                    "maxstep": settings.get("maxstepbdf"),
                }
            )
    params = _parameter_snapshot(model)
    tfinal_expr = params.get("tfinal", "0[s]")
    match = re.search(r"[-+0-9.eE]+", tfinal_expr)
    if match:
        solver["tfinal"] = float(match.group(0))
    return study, solver

def read_mph_snapshot(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ContractError(f"MPH does not exist: {source}")
    try:
        with zipfile.ZipFile(source) as archive:
            model = json.loads(archive.read("smodel.json").decode("utf-8"))
            dmodel_xml = archive.read("dmodel.xml").decode("utf-8", errors="replace")
    except (KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read COMSOL MPH archive {source}: {exc}") from exc
    component = _component(model)
    physics = {
        str(node.get("tag")): _physics_snapshot(node)
        for node in component.get("nodes", []) or []
        if isinstance(node, Mapping) and node.get("apiClass") == "Physics"
    }
    for tag, units in _physics_units_from_dmodel(dmodel_xml).items():
        if tag in physics:
            physics[tag]["units"] = units
    study, solver = _study_and_solver_snapshot(model, dmodel_xml)
    boundary_conditions: list[dict[str, Any]] = []
    initial_conditions: list[dict[str, Any]] = []
    for tag, physics_node in (
        (str(node.get("tag")), node)
        for node in component.get("nodes", []) or []
        if isinstance(node, Mapping) and node.get("apiClass") == "Physics"
    ):
        for feature in physics_node.get("nodes", []) or []:
            if not isinstance(feature, Mapping):
                continue
            label = str(feature.get("label") or "")
            item = {"physics": tag, "tag": feature.get("tag"), "type": label}
            if "zero flux" in label.lower() or "flux" in label.lower():
                boundary_conditions.append(item)
            if "initial" in label.lower():
                initial_conditions.append(item)
    return {
        "model_name": str(model.get("displayLabel") or model.get("label") or ""),
        "parameters": _parameter_snapshot(model),
        "variables": _variables_snapshot(component),
        "physics": physics,
        "boundary_conditions": boundary_conditions,
        "initial_conditions": initial_conditions,
        "mesh": _mesh_snapshot(component),
        "study": study,
        "solver": solver,
        "source": {
            "path": source.name,
            "format": "COMSOL MPH smodel.json + dmodel.xml",
        },
    }
