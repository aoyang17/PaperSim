"""Deterministic build-only and solve-only Java generation from an approved IR."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable

from .case_contracts import IR, java_class_name
from .case_store import CaseLayout
from .contracts import ContractError


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _java_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _parameter_expression(item) -> str:
    if item.expression:
        expression = str(item.expression).strip()
        return expression
    value = item.value
    assert value is not None
    units = str(item.units or "1").strip()
    if units == "1" or re.search(r"\[[^\]]+\]", str(value)):
        return str(value)
    return f"{value}[{units}]"


def _parameter_calls(ir: IR) -> str:
    lines: list[str] = []
    for item in ir.profile.parameters:
        lines.append(
            "    parameter("
            + ", ".join(
                (
                    _java_string(item.comsol_name),
                    _java_string(_parameter_expression(item)),
                    _java_string(item.meaning),
                )
            )
            + ");"
        )
    return "\n".join(lines)


def _variable_calls(ir: IR) -> str:
    lines: list[str] = []
    current_group = ""
    for item in ir.profile.variables:
        if item.group != current_group:
            if current_group:
                lines.append("")
            lines.append(f"    // {item.group}")
            current_group = item.group
        lines.append(
            "    variable("
            + ", ".join(
                (
                    _java_string(item.group),
                    _java_string(item.comsol_name),
                    _java_string(item.expression),
                    _java_string(item.description),
                )
            )
            + ");"
        )
    return "\n".join(lines)


def _delta_values(ir: IR) -> str:
    values = ir.profile.solver.settings.get("delta_values")
    if not isinstance(values, list) or not values:
        raise ContractError("Kobayashi profile requires solver.settings.delta_values")
    # COMSOL accepts a comma-separated parameter list in plistarr.
    return ",".join(str(value) for value in values)


def _generated_header(ir: IR) -> str:
    lines = [
        f"Case: {ir.case_id}",
        f"Iteration: iter{ir.iteration:03d}",
        f"Profile SHA-256: {ir.profile_sha256}",
        f"IR SHA-256: {ir.ir_hash}",
        "",
        "Equation-to-feature mapping:",
    ]
    for equation in ir.profile.equations:
        features = ", ".join(equation.comsol_features) or "(not a COMSOL feature)"
        lines.append(f"  {equation.id} [{equation.classification.value}] -> {features}")
    return "/**\n" + "\n".join(" * " + line for line in lines) + "\n */"


def _template_path(ir: IR, key: str) -> Path:
    value = ir.profile.comsol_templates.get(key)
    if not value:
        raise ContractError(f"profile.comsol_templates.{key} is required")
    path = (_repository_root() / value).resolve()
    if not path.is_file():
        raise ContractError(f"Java template does not exist: {path}")
    return path


def _replace_once(text: str, marker: str, value: str) -> str:
    if text.count(marker) != 1:
        raise ContractError(f"template marker {marker!r} must occur exactly once")
    return text.replace(marker, value)


def generate_iteration_java(ir: IR, layout: CaseLayout) -> tuple[Path, Path]:
    build_class = java_class_name(ir.case_id, "Build")
    solve_class = java_class_name(ir.case_id, "Solve")
    build_mph = layout.built_mph(ir.iteration).name
    solved_mph = layout.solved_mph(ir.iteration).name
    global_csv = f"iter{ir.iteration:03d}_global.csv"
    fields_csv = f"iter{ir.iteration:03d}_fields.csv"
    model_name = "".join(part.capitalize() for part in _case_words(ir.case_id))

    build = _template_path(ir, "build").read_text(encoding="utf-8")
    build = _replace_once(build, "/*__GENERATED_HEADER__*/", _generated_header(ir))
    build = _replace_once(build, "__BUILD_CLASS__", build_class)
    build = _replace_once(build, "__MODEL_NAME__", model_name)
    build = _replace_once(build, "__MODEL_LABEL__", f"{ir.case_id} iter{ir.iteration:03d} build-only")
    build = _replace_once(build, "__BUILD_MPH__", build_mph)
    build = _replace_once(build, "/*__PARAMETER_CALLS__*/", _parameter_calls(ir))
    build = _replace_once(build, "/*__VARIABLE_CALLS__*/", _variable_calls(ir))
    delta_values = _delta_values(ir)
    build = _replace_once(build, "__DELTA_VALUES__", delta_values)

    solve = _template_path(ir, "solve").read_text(encoding="utf-8")
    solve = _replace_once(solve, "/*__GENERATED_HEADER__*/", _generated_header(ir))
    solve = _replace_once(solve, "__SOLVE_CLASS__", solve_class)
    solve = _replace_once(solve, "__MODEL_NAME__", model_name)
    solve = _replace_once(solve, "__BUILD_MPH__", build_mph)
    solve = _replace_once(solve, "__SOLVED_MPH__", solved_mph)
    solve = _replace_once(solve, "__GLOBAL_CSV__", global_csv)
    solve = _replace_once(solve, "__FIELDS_CSV__", fields_csv)

    _validate_generated_sources(ir, build, solve)
    layout.build_java(ir.iteration).write_text(build, encoding="utf-8")
    layout.solve_java(ir.iteration).write_text(solve, encoding="utf-8")
    return layout.build_java(ir.iteration), layout.solve_java(ir.iteration)


def _case_words(case_id: str) -> Iterable[str]:
    surname_and_year, _, topic = case_id.partition("_")
    match = re.fullmatch(r"([a-z]+)([0-9]{4})", surname_and_year)
    if not match:
        raise ContractError(f"invalid case id: {case_id}")
    return (match.group(1), match.group(2), topic)


def _validate_generated_sources(ir: IR, build: str, solve: str) -> None:
    if build.count(".save(") != 1:
        raise ContractError("build Java must save exactly one unsolved MPH")
    if ".runAll(" in build or ".study(\"std1\").run()" in build or "solved.mph" in build:
        raise ContractError("build Java must not solve or save a solved MPH")
    if "Parametric" not in build or 'set("pname", new String[]{"delta"})' not in build:
        raise ContractError("build Java must contain one delta parametric sweep")
    if ".study(\"std1\").run()" not in solve:
        raise ContractError("solve Java must call runAll")
    if ".save(" not in solve or "solved.mph" not in solve:
        raise ContractError("solve Java must save a solved MPH")
    if ".param().set(" in solve or ".physics()" in solve:
        raise ContractError("solve Java must not rebuild parameters or physics")
    missing_parameters = [
        item.comsol_name for item in ir.profile.parameters if item.comsol_name not in build
    ]
    if missing_parameters:
        raise ContractError(f"build Java does not define IR parameters: {missing_parameters}")
    missing_variables = [
        item.comsol_name for item in ir.profile.variables if item.comsol_name not in build
    ]
    if missing_variables:
        raise ContractError(f"build Java does not define IR variables: {missing_variables}")
    if re.search(r'variable\([^\n]+\);\n', build) and '.set(name, expression, description)' not in build:
        raise ContractError("build Java variables must use COMSOL Variable Description fields")
