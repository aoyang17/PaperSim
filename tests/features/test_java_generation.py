from __future__ import annotations

from papersim.case_java import generate_iteration_java


def test_generated_build_and_solve_are_separated(synthetic_case):
    _, layout, _, _, ir = synthetic_case
    build, solve = generate_iteration_java(ir, layout)
    build_text = build.read_text(encoding="utf-8")
    solve_text = solve.read_text(encoding="utf-8")
    assert "public final class Kobayashi1993DendriteBuild" in build_text
    assert "Parametric" in build_text
    assert 'prop("Units").set("SourceTermQuantity", "none")' in build_text
    assert 'set("pname", new String[]{"delta"})' in build_text
    assert ".runAll(" not in build_text
    assert build_text.count(".save(") == 1
    assert "public final class Kobayashi1993DendriteSolve" in solve_text
    assert '.study("std1").run()' in solve_text
    assert '.set("data", "dset2")' in solve_text
    assert '"export-only".equals(args[0])' in solve_text
    assert ".param().set(" not in solve_text
    for parameter in ir.profile.parameters:
        assert parameter.comsol_name in build_text
    for variable in ir.profile.variables:
        assert variable.comsol_name in build_text
        assert variable.description in build_text
