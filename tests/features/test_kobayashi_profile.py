from __future__ import annotations

from papersim.case_contracts import EquationClass


def test_kobayashi_profile_has_required_eq3_eq5_fig7_contract(kobayashi_profile):
    assert kobayashi_profile.case_id == "kobayashi1993_dendrite"
    controls = [item for item in kobayashi_profile.equations if item.classification == EquationClass.CONTROL]
    assert {item.id for item in controls} == {"eq3", "eq5"}
    assert {item.comsol_name for item in kobayashi_profile.parameters} >= {"L", "epsbar", "tau", "Klatent", "delta"}
    assert kobayashi_profile.solver.settings["delta_values"] == [0, 0.005, 0.01, 0.02, 0.05]
    assert len(kobayashi_profile.acceptance) == 12
