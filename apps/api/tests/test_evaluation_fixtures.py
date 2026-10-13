import json
from pathlib import Path
from typing import cast

from vetoq.contracts import FAMILIES
from vetoq.inspection import inspect

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((FIXTURES / name).read_text(encoding="utf-8")),
    )


def test_smoke_corpus_has_three_cases_per_official_family() -> None:
    document = load("attack_families.json")
    assert document["kind"] == "evaluation-fixture"
    cases = document["cases"]
    assert isinstance(cases, list)
    counts = {family: 0 for family in FAMILIES}
    for case in cases:
        assert isinstance(case, dict)
        counts[str(case["family"])] += 1
        _, findings, complete = inspect(str(case["id"]), str(case["text"]))
        assert complete
        assert str(case["family"]) in {str(finding["family"]) for finding in findings}
    assert counts == {family: 3 for family in FAMILIES}


def test_smoke_corpus_has_twenty_benign_controls() -> None:
    document = load("benign_support.json")
    assert document["kind"] == "evaluation-fixture"
    cases = document["cases"]
    assert isinstance(cases, list)
    assert len(cases) == 20
    for case in cases:
        assert isinstance(case, dict)
        _, findings, complete = inspect(str(case["id"]), str(case["text"]))
        assert complete
        assert findings == []
