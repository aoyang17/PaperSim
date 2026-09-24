from __future__ import annotations

import json
from pathlib import Path
import zipfile

from papersim.case_mph import read_mph_snapshot


def test_mph_readback_parses_persisted_physics(tmp_path: Path):
    smodel = {
        "displayLabel": "Model",
        "nodes": [
            {
                "apiClass": "NonEntity",
                "tag": "glob",
                "nodes": [
                    {
                        "apiClass": "ModelParamGroup",
                        "tag": "default",
                        "settings": [{"name": "tfinal", "value": "1.4[s]"}],
                    }
                ],
            },
            {
                "apiClass": "ModelNode",
                "tag": "comp1",
                "nodes": [
                    {
                        "apiClass": "NonEntity",
                        "tag": "nonEntity2",
                        "nodes": [
                            {
                                "apiClass": "Expr",
                                "tag": "v_source",
                                "settings": [{"name": "phaseSource", "value": "p", "description": "source"}],
                            }
                        ],
                    },
                    {"apiClass": "MeshSequence", "tag": "mesh1", "nodes": [{"label": "Mapped 1"}]},
                    {
                        "apiClass": "Physics",
                        "tag": "gp",
                        "apiType": "GeneralFormPDE",
                        "settings": [
                            {"name": "DependentVariableQuantity", "value": "none"},
                            {"name": "SourceTermQuantity", "value": "none"},
                            {"name": "u", "value": ["1", "p"]},
                        ],
                        "nodes": [
                            {"label": "General Form PDE 1", "tag": "gfeq1"},
                            {"label": "Zero Flux 1", "tag": "zflx1"},
                            {"label": "Initial Values 1", "tag": "init1"},
                        ],
                    },
                ],
            },
            {
                "apiClass": "Study",
                "tag": "std1",
                "nodes": [
                    {
                        "apiClass": "SolverSequence",
                        "tag": "sol1",
                        "nodes": [
                            {
                                "tag": "t1",
                                "type": "Time_dependent_solver",
                                "settings": [
                                    {"name": "timemethod", "value": "BDF"},
                                    {"name": "rtol", "value": "0.001"},
                                ],
                            }
                        ],
                    }
                ],
            },
        ],
    }
    dmodel = '''<Model><Physics tag="gp"><PhysicsProp tag="Units">
    <param param="CustomDependentVariableUnit" value="1|1,'1'"/>
    <param param="CustomSourceTermUnit" value="1|1,'1/s'"/>
    </PhysicsProp><Study><StudyFeature tag="param">
    <propertyValue valueMatrix="1|1,'delta'" name="p:pname"/>
    <propertyValue name="p:plistarr" ValueRows="1,'0\\,0.005\\,0.01'"/>
    </StudyFeature></Study></Physics></Model>'''
    path = tmp_path / "model.mph"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("smodel.json", json.dumps(smodel))
        archive.writestr("dmodel.xml", dmodel)
    snapshot = read_mph_snapshot(path)
    assert snapshot["parameters"]["tfinal"] == "1.4[s]"
    assert snapshot["variables"]["v_source"]["phaseSource"]["description"] == "source"
    assert snapshot["physics"]["gp"]["dependent"] == ["p"]
    assert snapshot["physics"]["gp"]["units"] == {"dependent_unit": "1", "source_unit": "1/s"}
    assert snapshot["study"]["parametric"] == {"parameter": "delta", "values": [0.0, 0.005, 0.01]}
    assert snapshot["mesh"]["type"] == "Mapped"
