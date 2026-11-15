"""The data file the macOS input method bundles (scripts/export_mac_data.py)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from sing_khmer_engine.lookup import Engine

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_mac_data.py"
_spec = importlib.util.spec_from_file_location("export_mac_data", _SCRIPT)
export_mac_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_mac_data)


def test_data_carries_everything_the_swift_engine_reads():
    engine = Engine()
    data = json.loads(json.dumps(export_mac_data.build_data(engine), ensure_ascii=False))

    assert data["version"] == export_mac_data.FORMAT_VERSION
    assert set(data["index"]) == set(engine.index)
    assert data["index"]["nh"][0] == {"khmer": "ខ្ញុំ", "score": 5.0, "source": "collected"}
    for key, cands in engine.index.items():           # ranking order must survive the export
        assert [c["khmer"] for c in data["index"][key]] == [c.khmer for c in cands]
    assert set(data["khmer_words"]) == {entry.khmer for entry in engine.vocab}
    assert "hello" in data["english"]


def test_golden_inputs_are_deterministic_and_unique():
    engine = Engine()
    first = export_mac_data.golden_inputs(engine)
    assert first == export_mac_data.golden_inputs(engine)
    assert len(first) == len(set(first))
    assert set(engine.index) <= set(first)             # every known spelling is covered
