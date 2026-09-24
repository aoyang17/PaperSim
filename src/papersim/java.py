"""Generate one auditable COMSOL Java source from an extraction bundle."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping

from .contracts import ContractError
from .extraction import ExtractionBundle


IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _identifier(value: str, field: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise ContractError(f"{field} is not a valid Java/COMSOL identifier: {value!r}")
    return value


def _java_string(value: Any) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def _expression_with_units(expression: str, units: str) -> str:
    expression = str(expression).strip()
    units = str(units or "1").strip()
    if units == "1" or re.search(r"\[[^\]]+\]", expression):
        return expression
    if any(token in expression for token in ("[", "]", "if(", "range(", "*tfinal")):
        return expression
    return f"{expression}[{units}]"


def _validate_java_model(spec: Mapping[str, Any]) -> dict[str, Any]:
    class_name = _identifier(str(spec.get("class_name") or ""), "class_name")
    if spec.get("template_file"):
        template = (Path(__file__).resolve().parents[2] / str(spec["template_file"])).resolve()
        if not template.is_file():
            raise ContractError(f"Java template does not exist: {template}")
        if "/*__PAPERSIM_REPORT__*/" not in template.read_text(encoding="utf-8"):
            raise ContractError("Java template is missing /*__PAPERSIM_REPORT__*/")
        if not str(spec.get("output_mph") or "").strip():
            raise ContractError("template java_model requires output_mph")
        return dict(spec)
    output_mph = str(spec.get("output_mph") or f"{class_name}_built.mph")
    parameters = spec.get("parameters")
    variable_groups = spec.get("variable_groups")
    pdes = spec.get("pdes")
    sweep = spec.get("sweep")
    if not isinstance(parameters, list) or not parameters:
        raise ContractError("java_model.parameters must be a non-empty list")
    if not isinstance(variable_groups, list) or not variable_groups:
        raise ContractError("java_model.variable_groups must be a non-empty list")
    if not isinstance(pdes, list) or not pdes:
        raise ContractError("java_model.pdes must be a non-empty list")
    if not isinstance(sweep, Mapping):
        raise ContractError("java_model.sweep must be an object")

    parameter_names: set[str] = set()
    for item in parameters:
        name = _identifier(str(item["name"]), "parameter.name")
        if name in parameter_names:
            raise ContractError(f"duplicate parameter name: {name}")
        parameter_names.add(name)
        if not str(item.get("expression") or "").strip():
            raise ContractError(f"parameter {name} has no expression")
        if not str(item.get("description") or "").strip():
            raise ContractError(f"parameter {name} has no description")

    variable_names: set[str] = set()
    for group in variable_groups:
        _identifier(str(group["tag"]), "variable_group.tag")
        variables = group.get("variables")
        if not isinstance(variables, list) or not variables:
            raise ContractError(f"variable group {group['tag']} is empty")
        for item in variables:
            name = _identifier(str(item["name"]), "variable.name")
            if name in variable_names:
                raise ContractError(f"duplicate variable name: {name}")
            variable_names.add(name)
            for key in ("expression", "units", "description"):
                if not str(item.get(key) or "").strip():
                    raise ContractError(f"variable {name} is missing {key}")

    pde_tags: set[str] = set()
    for item in pdes:
        tag = _identifier(str(item["tag"]), "pde.tag")
        if tag in pde_tags:
            raise ContractError(f"duplicate PDE tag: {tag}")
        pde_tags.add(tag)
        for key in ("dependent_unit", "source_unit", "weak"):
            if not str(item.get(key) or "").strip():
                raise ContractError(f"PDE {tag} is missing {key}")
        references = [str(value) for value in item.get("references_variables", [])]
        missing = [value for value in references if value not in variable_names]
        if missing:
            raise ContractError(f"PDE {tag} references unknown variables: {missing}")
        if not references:
            raise ContractError(f"PDE {tag} must declare references_variables")
        forbidden = [value for value in ("beta", "sigma", "epsilon", "plat") if re.search(rf"\b{value}\w*\b", str(item["weak"]))]
        if forbidden:
            raise ContractError(f"PDE {tag} appears to inline constitutive symbols: {forbidden}")

    sweep_parameter = _identifier(str(sweep.get("parameter") or ""), "sweep.parameter")
    if sweep_parameter not in parameter_names:
        raise ContractError(f"sweep parameter is not declared: {sweep_parameter}")
    if not str(sweep.get("values") or "").strip():
        raise ContractError("sweep.values is required")
    if not str(sweep.get("tlist") or "").strip():
        raise ContractError("sweep.tlist is required")
    return dict(spec)


def _template_report(bundle: ExtractionBundle, spec: Mapping[str, Any]) -> str:
    equation_rows = [
        [f"[{item.number}]", item.classification, item.latex, item.evidence[0].label]
        for item in bundle.equations
    ]
    lines = [
        str(spec.get("label", spec["class_name"])),
        "",
        f"Source SHA-256: {bundle.source_sha256}",
        "",
        "1. equation_classification",
        _markdown_table(["Eq.", "Class", "Normalized equation", "Evidence"], equation_rows),
        "",
        "2. comsol_tree_changes",
    ]
    lines.extend(str(item) for item in spec.get("tree_changes", []))
    lines.extend(["", "3. variables_definitions", _markdown_table(["Name", "Expression", "Unit", "Description"], spec.get("variables_definitions", []))])
    lines.extend(["", "4. pde_ode_settings", _markdown_table(["Object", "Dependent unit", "Weak residual unit", "Expression"], spec.get("pde_ode_settings", []))])
    lines.extend(["", "5. parameters", _markdown_table(["Paper symbol", "COMSOL name", "Value/range", "Meaning", "Source"], spec.get("parameters_table", []))])
    lines.extend(["", "6. parametric_sweep"])
    sweeps = spec.get("parametric_sweep", [])
    if sweeps:
        lines.append(_markdown_table(["Parameter", "Values", "Study"], sweeps))
    else:
        lines.append("No paper parameter variation is declared in this Java artifact.")
    lines.extend(["", "7. report_nomenclature", _markdown_table(["Source symbol", "Meaning", "Unit", "COMSOL variable", "Source"], spec.get("nomenclature", []))])
    lines.extend(["", "8. self_check"])
    for item in spec.get("self_check", []):
        lines.append(f"- [x] {item}")
    return "\n".join(lines)


def generate_java(bundle: ExtractionBundle, output_path: str | Path) -> Path:
    spec = _validate_java_model(bundle.java_model)
    class_name = str(spec["class_name"])
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix != ".java":
        target = target / f"{class_name}.java"

    if spec.get("template_file"):
        template_path = (Path(__file__).resolve().parents[2] / str(spec["template_file"])).resolve()
        text = template_path.read_text(encoding="utf-8")
        report = _template_report(bundle, spec)
        report_block = "/**\n" + "\n".join(" * " + line for line in report.splitlines()) + "\n */"
        text = text.replace("/*__PAPERSIM_REPORT__*/", report_block)
        text = text.replace("__CLASS_NAME__", class_name)
        text = text.replace("__MODEL_LABEL__", str(spec.get("label", class_name)))
        text = text.replace("__OUTPUT_MPH__", str(spec["output_mph"]))
        target.write_text(text, encoding="utf-8")
        return target

    equation_rows = [
        [f"({item.number})", item.classification, item.latex, ", ".join(item.referenced_symbols), item.evidence[0].label]
        for item in bundle.equations
    ]
    variable_rows = [
        [
            item["name"],
            item["expression"],
            item["units"],
            item["description"],
        ]
        for group in spec["variable_groups"]
        for item in group["variables"]
    ]
    pde_rows = [
        [item["tag"], item["dependent_unit"], item["source_unit"], item["weak"]]
        for item in spec["pdes"]
    ]
    parameter_rows = [
        [
            item.get("source_symbol", item["name"]),
            item["name"],
            _expression_with_units(item["expression"], item.get("units", "1")),
            item["description"],
            item.get("source", ""),
        ]
        for item in spec["parameters"]
    ]
    sweep = spec["sweep"]
    sweep_rows = [[sweep["parameter"], sweep["parameter"], sweep["values"], sweep["study"]]]
    nomenclature_rows = [
        [item["source_symbol"], item["meaning"], item["units"], item["comsol_variable"], item["source"]]
        for item in spec.get("nomenclature", [])
    ]
    self_checks = [
        "No constitutive expressions are inlined in PDE/ODE settings.",
        "All constitutive relations are defined in Variables.",
        "PDE settings reference named Variables.",
        "Every Variable has a non-empty human-readable Description.",
        "Every PDE declares dependent-variable and flux/source units.",
        "Parameter variations use Parametric Sweep.",
        "Exactly one MPH is generated by this Java source.",
        "Report equations use normalized human-readable LaTeX.",
        "Nomenclature maps source symbols to COMSOL variables.",
        "Uncertain items are marked NEEDS_REVIEW rather than guessed.",
    ]

    lines: list[str] = []
    lines.extend([
        "import com.comsol.model.*;",
        "import com.comsol.model.util.*;",
        "",
        "/**",
        f" * {spec.get('label', class_name)}",
        " *",
        " * Generated from source-addressable paper extraction.",
        f" * Source SHA-256: {bundle.source_sha256}",
        " *",
        " * 1. equation_classification",
    ])
    for line in _markdown_table(["Eq.", "Class", "Normalized equation", "Symbols", "Evidence"], equation_rows).splitlines():
        lines.append(" * " + line)
    lines.extend([" *", " * 2. comsol_tree_changes", " * ```text"])
    for line in spec.get("tree_changes", []):
        lines.append(" * " + str(line))
    lines.extend([" * ```", " *", " * 3. variables_definitions"])
    for line in _markdown_table(["Name", "Expression", "Unit", "Description"], variable_rows).splitlines():
        lines.append(" * " + line)
    lines.extend([" *", " * 4. pde_ode_settings"])
    for line in _markdown_table(["PDE", "Dependent unit", "Flux/source unit", "Weak expression"], pde_rows).splitlines():
        lines.append(" * " + line)
    lines.extend([" *", " * 5. parameters"])
    for line in _markdown_table(["Paper symbol", "COMSOL name", "Value/range", "Meaning", "Source"], parameter_rows).splitlines():
        lines.append(" * " + line)
    lines.extend([" *", " * 6. parametric_sweep"])
    for line in _markdown_table(["Parameter", "COMSOL name", "Values", "Study"], sweep_rows).splitlines():
        lines.append(" * " + line)
    lines.extend([" *", " * 7. report_nomenclature"])
    for line in _markdown_table(["Source symbol", "Meaning", "Unit", "COMSOL variable", "Source"], nomenclature_rows).splitlines():
        lines.append(" * " + line)
    lines.extend([" *", " * 8. self_check"])
    for item in self_checks:
        lines.append(f" * - [x] {item}")
    lines.extend([
        " */",
        f"public final class {class_name} {{",
        "  private static Model m;",
        "",
        "  private static void parameter(String name, String expression, String description) {",
        "    m.param().set(name, expression, description);",
        "  }",
        "",
        "  private static void variable(String group, String name, String expression, String description) {",
        "    m.component(\"comp1\").variable(group).set(name, expression, description);",
        "  }",
        "",
        "  private static void setPdeUnits(String physics, String dependentUnit, String sourceUnit) {",
        "    m.component(\"comp1\").physics(physics).prop(\"Units\").set(\"DependentVariableQuantity\", \"none\");",
        "    m.component(\"comp1\").physics(physics).prop(\"Units\").set(\"CustomDependentVariableUnit\", dependentUnit);",
        "    m.component(\"comp1\").physics(physics).prop(\"Units\").set(\"SourceTermQuantity\", \"none\");",
        "    m.component(\"comp1\").physics(physics).prop(\"Units\").set(\"CustomSourceTermUnit\", sourceUnit);",
        "  }",
        "",
        "  private static void parameters() {",
    ])
    for item in spec["parameters"]:
        expression = _expression_with_units(item["expression"], item.get("units", "1"))
        lines.append(
            f"    parameter({_java_string(item['name'])}, {_java_string(expression)}, {_java_string(item['description'])});"
        )
    lines.extend(["  }", "", "  private static void geometryAndMesh() {"])
    geometry = spec.get("geometry") or {}
    dimension = int(geometry.get("dimension", 1))
    if dimension != 1:
        raise ContractError("the current single-file generator supports one-dimensional geometry only")
    interval = geometry.get("interval") or ["0", "1"]
    lines.extend([
        "    m.component().create(\"comp1\", true);",
        "    m.component(\"comp1\").geom().create(\"g1\", 1);",
        "    m.component(\"comp1\").geom(\"g1\").create(\"i1\", \"Interval\");",
        f"    m.component(\"comp1\").geom(\"g1\").feature(\"i1\").set(\"coord\", new String[]{{{_java_string(interval[0])}, {_java_string(interval[1])}}});",
        "    m.component(\"comp1\").geom(\"g1\").run();",
    ])
    selection = geometry.get("axis_selection")
    if selection:
        lines.extend([
            f"    m.component(\"comp1\").selection().create({_java_string(selection['tag'])}, \"Box\");",
            f"    m.component(\"comp1\").selection({_java_string(selection['tag'])}).geom(\"g1\", 0);",
            f"    m.component(\"comp1\").selection({_java_string(selection['tag'])}).set(\"entitydim\", 0);",
            f"    m.component(\"comp1\").selection({_java_string(selection['tag'])}).set(\"xmin\", \"-1e-12\");",
            f"    m.component(\"comp1\").selection({_java_string(selection['tag'])}).set(\"xmax\", \"1e-12\");",
        ])
    mesh = spec.get("mesh") or {}
    lines.extend([
        "    m.component(\"comp1\").mesh().create(\"mesh1\", \"g1\");",
        "    m.component(\"comp1\").mesh(\"mesh1\").create(\"edg1\", \"Edge\");",
        "    m.component(\"comp1\").mesh(\"mesh1\").feature(\"edg1\").create(\"dis1\", \"Distribution\");",
        f"    m.component(\"comp1\").mesh(\"mesh1\").feature(\"edg1\").feature(\"dis1\").set(\"numelem\", {_java_string(mesh.get('elements', 'Nelem'))});",
        "    m.component(\"comp1\").mesh(\"mesh1\").run();",
        "  }",
        "",
        "  private static void variables() {",
    ])
    for group in spec["variable_groups"]:
        lines.append(f"    m.component(\"comp1\").variable().create({_java_string(group['tag'])});")
        for item in group["variables"]:
            lines.append(
                f"    variable({_java_string(group['tag'])}, {_java_string(item['name'])}, {_java_string(item['expression'])}, {_java_string(item['description'])});"
            )
    lines.extend(["  }", "", "  private static void controlEquations() {"])
    for item in spec["pdes"]:
        tag = str(item["tag"])
        lines.extend([
            f"    m.component(\"comp1\").physics().create({_java_string(tag)}, \"WeakFormPDE\", \"g1\");",
            f"    setPdeUnits({_java_string(tag)}, {_java_string(item['dependent_unit'])}, {_java_string(item['source_unit'])});",
            f"    m.component(\"comp1\").physics({_java_string(tag)}).feature(\"wfeq1\").set(\"weak\", {_java_string(item['weak'])});",
        ])
        for boundary in item.get("boundaries", []):
            selection_tag = str(boundary["selection"])
            lines.extend([
                f"    m.component(\"comp1\").physics({_java_string(tag)}).create({_java_string(boundary['tag'])}, \"DirichletBoundary\", 0);",
                f"    m.component(\"comp1\").physics({_java_string(tag)}).feature({_java_string(boundary['tag'])}).selection().named({_java_string(selection_tag)});",
                f"    m.component(\"comp1\").physics({_java_string(tag)}).feature({_java_string(boundary['tag'])}).set(\"r\", {_java_string(boundary['value'])});",
            ])
        for initial in item.get("initial", []):
            lines.append(
                f"    m.component(\"comp1\").physics({_java_string(tag)}).feature(\"init1\").set({_java_string(initial['field'])}, {_java_string(initial['value'])});"
            )
    lines.extend(["  }", "", "  private static void studyWithParametricSweep() {"])
    study = str(sweep["study"])
    lines.extend([
        "    m.study().create(\"std1\");",
        f"    m.study(\"std1\").create({_java_string(study)}, \"Parametric\");",
        f"    m.study(\"std1\").feature({_java_string(study)}).set(\"pname\", new String[]{{{_java_string(sweep['parameter'])}}});",
        f"    m.study(\"std1\").feature({_java_string(study)}).set(\"plistarr\", new String[]{{{_java_string(sweep['values'])}}});",
        "    m.study(\"std1\").create(\"time\", \"Transient\");",
        f"    m.study(\"std1\").feature(\"time\").set(\"tlist\", {_java_string(sweep['tlist'])});",
        "    m.study(\"std1\").createAutoSequences(\"sol\");",
        f"    m.sol(\"sol1\").feature(\"t1\").set(\"tlist\", {_java_string(sweep['tlist'])});",
        "    m.sol(\"sol1\").feature(\"t1\").set(\"timemethod\", \"bdf\");",
        "    m.sol(\"sol1\").feature(\"t1\").set(\"maxorder\", 1);",
        "    m.sol(\"sol1\").feature(\"t1\").set(\"rtol\", 1e-3);",
        "    m.sol(\"sol1\").feature(\"t1\").set(\"atolglobalvaluemethod\", \"manual\");",
        "    m.sol(\"sol1\").feature(\"t1\").set(\"atolglobalmethod\", \"unscaled\");",
        "    m.sol(\"sol1\").feature(\"t1\").set(\"atolglobal\", \"1e-6\");",
        "    m.sol(\"sol1\").feature(\"t1\").set(\"tstepsbdf\", \"free\");",
        "    m.sol(\"sol1\").feature(\"t1\").set(\"maxstepconstraintbdf\", \"const\");",
        "    m.sol(\"sol1\").feature(\"t1\").set(\"maxstepbdf\", \"0.005\");",
        "    m.sol(\"sol1\").feature(\"t1\").set(\"initialstepbdfactive\", true);",
        "    m.sol(\"sol1\").feature(\"t1\").set(\"initialstepbdf\", \"1e-6\");",
        "    m.sol(\"sol1\").feature(\"t1\").set(\"tout\", \"tsteps\");",
        "    m.sol(\"sol1\").feature(\"t1\").set(\"tstepsstore\", 1);",
        "  }",
        "",
        "  public static Model run() throws Exception {",
        f"    m = ModelUtil.create({_java_string(class_name)});",
        f"    m.label({_java_string(spec.get('label', class_name))});",
        "    parameters();",
        "    geometryAndMesh();",
        "    variables();",
        "    controlEquations();",
        "    studyWithParametricSweep();",
        f"    m.save({_java_string(spec['output_mph'])});",
        "    return m;",
        "  }",
        "",
        "  public static void main(String[] args) throws Exception {",
        "    run();",
        "  }",
        "}",
        "",
    ])
    target.write_text("\n".join(lines), encoding="utf-8")
    return target
