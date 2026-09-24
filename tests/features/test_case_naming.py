from __future__ import annotations

import pytest

from papersim.case_contracts import ContractError, java_class_name, make_case_id


def test_case_id_examples():
    assert make_case_id("Kobayashi", 1993, "dendrite") == "kobayashi1993_dendrite"
    assert make_case_id("Huang", 2013, "lithiation") == "huang2013_lithiation"
    assert make_case_id("Chen", 2014, "elastoplastic") == "chen2014_elastoplastic"


def test_case_id_rejects_bad_identity():
    with pytest.raises(ContractError):
        make_case_id("../Kobayashi", 1993, "dendrite")
    with pytest.raises(ContractError):
        make_case_id("Kobayashi", 93, "dendrite")
    with pytest.raises(ContractError):
        make_case_id("Kobayashi", 1993, "two words")


def test_java_class_name_is_derived():
    assert java_class_name("kobayashi1993_dendrite", "Build") == "Kobayashi1993DendriteBuild"
    assert java_class_name("kobayashi1993_dendrite", "Solve") == "Kobayashi1993DendriteSolve"
