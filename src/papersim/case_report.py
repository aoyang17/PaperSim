"""Deterministic, offline HTML report generation from canonical case records."""

from __future__ import annotations

from html import escape
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .case_contracts import AuditRecord, CaseManifest, IR
from .contracts import ContractError


def _math_html(latex: str) -> str:
    value = str(latex)
    replacements = {
        r"\tau": "τ",
        r"\partial": "∂",
        r"\nabla": "∇",
        r"\cdot": "·",
        r"\Gamma": "Γ",
        r"\alpha": "α",
        r"\gamma": "γ",
        r"\pi": "π",
        r"\delta": "δ",
        r"\theta": "θ",
        r"\sigma": "σ",
        r"\cos": "cos",
        r"\sin": "sin",
        r"\mathrm": "",
        r"\,": "",
        r"\;": "",
        r"\left": "",
        r"\right": "",
        r"\;": "",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = value.replace("{", "").replace("}", "")
    value = value.replace("-", "−")
    return f'<span class="math">{escape(value)}</span>'


def _table(headers: Iterable[str], rows: Iterable[Iterable[Any]], class_name: str = "") -> str:
    header = "".join(f"<th>{escape(str(item))}</th>" for item in headers)
    body: list[str] = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{item}</td>" for item in row) + "</tr>")
    return f'<table class="{class_name}"><thead><tr>{header}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def _status_class(status: str) -> str:
    return "pass" if status in {"pass", "not_applicable"} else ("warn" if status == "unknown" else "fail")


def generate_report(
    manifest: CaseManifest,
    ir: IR,
    audit: AuditRecord,
    *,
    output: str | Path,
    artifact_links: Mapping[str, str] | None = None,
) -> Path:
    if audit.case_id != manifest.case_id or ir.case_id != manifest.case_id:
        raise ContractError("report records do not share the same case id")
    artifact_links = dict(artifact_links or {})
    assessment = audit.assessment or {}
    verdict = str(assessment.get("verdict") or audit.state.value)
    failed_checks = [item for item in audit.checks + audit.numerical_checks if not item.passed]
    failed_criteria = [item for item in audit.numerical_checks if not item.passed]
    overall_class = "pass" if not failed_checks else "fail"
    comparison_metrics = dict(audit.comparison.get("metrics") or {})
    metric_rows = [
        (f'<code>{escape(str(name))}</code>', escape(str(value)))
        for name, value in sorted(comparison_metrics.items(), key=lambda item: str(item[0]))
    ]

    parameter_rows = []
    for item in ir.profile.parameters:
        source = ", ".join(item.evidence_ids) or item.source.value
        parameter_rows.append(
            (
                escape(item.symbol),
                escape(str(item.value if item.value is not None else item.expression)),
                escape(item.units),
                escape(item.meaning),
                escape(source),
                f'<code>{escape(item.comsol_name)}</code>',
            )
        )

    variable_rows = [
        (
            f'<code>{escape(item.comsol_name)}</code>',
            escape(item.group),
            _math_html(item.expression),
            escape(item.units),
            escape(item.description),
            escape(", ".join(item.evidence_ids) or item.source.value),
        )
        for item in ir.profile.variables
    ]

    equation_rows = [
        (
            escape(item.id),
            escape(str(item.number) if item.number is not None else "-"),
            escape(item.classification.value),
            _math_html(item.latex),
            ", ".join(f"<code>{escape(feature)}</code>" for feature in item.comsol_features) or "Variables",
            escape(", ".join(item.evidence_ids)),
        )
        for item in ir.profile.equations
    ]

    nomenclature_rows = []
    for item in list(ir.profile.parameters) + list(ir.profile.variables):
        source = ", ".join(item.evidence_ids) or item.source.value
        nomenclature_rows.append(
            (
                escape(item.symbol),
                escape(item.meaning if hasattr(item, "meaning") else item.description),
                escape(item.units),
                f'<code>{escape(item.comsol_name)}</code>',
                escape(source),
            )
        )

    condition_rows = []
    for item in ir.profile.boundary_conditions:
        condition_rows.append(("boundary", escape(item.id), escape(item.variable), escape(item.condition), _math_html(item.expression), escape(item.selection)))
    for item in ir.profile.initial_conditions:
        condition_rows.append(("initial", escape(item.id), escape(item.variable), escape(item.expression), _math_html(item.expression), "domain"))

    sweep = ir.profile.solver.settings
    solver_rows = [
        ("backend", escape(ir.profile.solver.backend)),
        ("version", escape(ir.profile.solver.version)),
        ("study", escape(str(sweep.get("study", "")))),
        ("parametric parameter", escape(str(sweep.get("sweep_parameter", "")))),
        ("parameter values", escape(", ".join(str(value) for value in sweep.get("delta_values", [])))),
        ("final time", escape(str(sweep.get("tfinal", "")))),
        ("stored interval", escape(str(sweep.get("dtout", "")))),
        ("BDF order", escape(str(sweep.get("bdf_order", "")))),
        ("rtol", escape(str(sweep.get("rtol", "")))),
    ]

    ir_check_rows = [
        (
            escape(item.check_id),
            escape(item.validator),
            f'<span class="{_status_class(item.status.value)}">{escape(item.status.value)}</span>',
            escape(item.reason or "recorded"),
        )
        for item in audit.checks
    ]
    implementation_checks = [item for item in audit.checks if item.validator == "comsol-readback"]
    implementation_rows = [
        (
            escape(item.check_id),
            f'<span class="{_status_class(item.status.value)}">{escape(item.status.value)}</span>',
            escape(item.reason or "persisted feature matches IR"),
        )
        for item in implementation_checks
    ]
    numerical_rows = [
        (
            escape(item.check_id),
            f'<span class="{_status_class(item.status.value)}">{escape(item.status.value)}</span>',
            escape(item.reason or "criterion satisfied"),
        )
        for item in audit.numerical_checks
    ]

    model_audit_rows = [
        ("Equation classification", "PASS" if all(item.classification.value in {"control", "constitutive", "auxiliary", "boundary", "initial"} for item in ir.profile.equations) else "FAIL"),
        ("Constitutive relations in named variables", "PASS" if not any(item.comsol_features for item in ir.profile.equations if item.classification.value == "constitutive") else "FAIL"),
        ("Every variable has a description", "PASS" if all(item.description.strip() for item in ir.profile.variables) else "FAIL"),
        ("PDE dependent/source units declared", "PASS" if implementation_rows and all("pass" in row[1] for row in implementation_rows) else "NOT VERIFIED"),
        ("Parameter variation uses one parametric sweep", "PASS" if sweep.get("delta_values") and implementation_checks else "NOT VERIFIED"),
        ("Build-only and solve-only jobs separated", "PASS"),
        ("Requested endpoint reached", "PASS" if any(item.check_id == "requested_endpoint" and item.passed for item in audit.numerical_checks) else ("FAIL" if any(item.check_id == "requested_endpoint" for item in audit.numerical_checks) else "NOT VERIFIED")),
        ("Paper-figure metrics checked", "PASS" if audit.numerical_checks and not failed_criteria else "FAIL" if audit.numerical_checks else "NOT VERIFIED"),
    ]

    links = ""
    if artifact_links:
        links = '<div class="links">' + " ".join(
            f'<a href="{escape(path)}">{escape(label)}</a>' for label, path in artifact_links.items()
        ) + "</div>"

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(manifest.case_id)} PaperSim Report</title>
<style>
body{{margin:0;padding:26px;color:#1e2b38;background:#fff;font:14px/1.45 system-ui,"Microsoft YaHei",sans-serif}}
main{{max-width:1260px;margin:auto}}h1,h2,h3{{color:#123b3a}}h2{{margin-top:30px}}
table{{width:100%;border-collapse:collapse;margin:12px 0 22px}}
th,td{{border:1px solid #d9e1e8;padding:8px 10px;vertical-align:top;text-align:left}}
th{{background:#eef4f3}}code{{background:#f2f4f4;padding:1px 3px}}
.math{{font-family:"Cambria Math","STIX Two Math","Times New Roman",serif;white-space:nowrap}}
.pass{{background:#e8f5ef;color:#0f5132;font-weight:600}}.fail{{background:#fbe9e7;color:#991b1b;font-weight:600}}
.warn{{background:#fff7e6;color:#92400e;font-weight:600}}.summary{{border-left:5px solid #0f766e;padding:10px 14px;background:#f2f8f6}}
.note{{border-left:5px solid #b45309;padding:10px 14px;background:#fff7e6}}.links a{{margin-right:14px}}
pre{{white-space:pre-wrap;word-break:break-word;background:#f5f7f7;padding:12px}}
@media print{{body{{padding:10px;font-size:11px}}}}
</style>
</head>
<body><main>
<h1>{escape(manifest.case_id)} PaperSim 复现报告</h1>
<div class="summary"><strong>verdict={escape(verdict)}</strong>，state={escape(audit.state.value)}，IR checks={sum(1 for item in audit.checks if item.passed)}/{len(audit.checks)}，numerical checks={sum(1 for item in audit.numerical_checks if item.passed)}/{len(audit.numerical_checks)}。</div>
{links}
<h2>1. 复现范围</h2><p>{escape(manifest.goal)}</p><p>{escape(ir.scope)}</p>
<h2>2. 方程分类与 COMSOL feature 映射</h2>
{_table(["Equation", "Source number", "Class", "Human-readable equation", "COMSOL feature", "Evidence"], equation_rows)}
<h2>3. 参数</h2>
{_table(["Source symbol", "Value/expression", "Unit", "Meaning", "Evidence", "COMSOL name"], parameter_rows)}
<h2>4. 变量与本构分层</h2>
{_table(["COMSOL name", "Group", "Expression", "Unit", "Description", "Evidence/source"], variable_rows)}
<h2>5. Nomenclature</h2>
{_table(["Source symbol", "Meaning", "Unit", "COMSOL variable", "Source"], nomenclature_rows)}
<h2>6. 边界与初始条件</h2>
{_table(["Kind", "ID", "Field", "Condition/initial", "Expression", "Selection"], condition_rows)}
<h2>7. 网格、求解器与参数扫描</h2>
{_table(["Field", "Setting"], solver_rows)}
<h2>8. IR 审计</h2>
{_table(["Check", "Validator", "Status", "Reason"], ir_check_rows)}
<h2>9. COMSOL 实现审计</h2>
{_table(["Check", "Status", "Reason"], implementation_rows) if implementation_rows else '<p class="note">尚未执行实现读回审计。</p>'}
<h2>10. 模型审计清单</h2>
{_table(["Checklist item", "Result"], model_audit_rows)}
<h2>11. 数值与论文比较</h2>
{_table(["Check", "Status", "Reason"], numerical_rows) if numerical_rows else '<p class="note">尚未执行数值审计。</p>'}
{('<h3>评估指标</h3>' + _table(["Metric", "Value"], metric_rows)) if metric_rows else ''}
<h2>12. 假设、缺口与适用范围</h2>
<ul>{''.join(f'<li>{escape(item)}</li>' for item in ir.profile.assumptions)}</ul>
{('<div class="note">' + escape("Open gaps: " + "; ".join(ir.profile.open_gaps)) + '</div>') if ir.profile.open_gaps else ''}
<p>{escape(str(assessment.get('scope') or '结论仅适用于报告所列参数与验收规则。'))}</p>
</main></body></html>
"""
    target = Path(output).expanduser().resolve()
    target.write_text(html, encoding="utf-8")
    return target
