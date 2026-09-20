import copy
import json
import subprocess
import sys

import pytest

from jev_diff import RecordError, compare, load_records, make_record


def pair():
    request = {
        "model": "jev-latest",
        "state": {"message": "I was charged twice."},
        "questions": {
            "queue": {
                "type": "choice",
                "instructions": "Which queue handles this ticket?",
                "criteria": {"billing": "Payments", "support": "Product help"},
            },
            "urgent": {"type": "noul", "instructions": "Is immediate attention required?"},
            "severity": {
                "type": "score",
                "instructions": "How severe is the issue?",
                "criteria": ["Cosmetic", "Workaround exists", "Blocked"],
            },
        },
    }
    response = {
        "model": "jev-1.13.0",
        "answers": {
            "queue": {
                "type": "choice",
                "choice": "billing",
                "confidence": 0.81,
                "probabilities": {"billing": 0.9, "support": 0.1},
            },
            "urgent": {"type": "noul", "noul": 0.89},
            "severity": {
                "type": "score",
                "score": 1.4,
                "confidence": 0.6,
                "legend": {"0": "Cosmetic", "1": "Workaround exists", "2": "Blocked"},
                "probabilities": {"0": 0.1, "1": 0.4, "2": 0.5},
            },
        },
        "usage": {"input_tokens": 150, "output_tokens": 12},
    }
    return request, response


@pytest.fixture
def records():
    before = {"ticket-1": make_record("ticket-1", *pair())}
    return before, copy.deepcopy(before)


def kinds(report):
    return [change["kind"] for change in report["changes"]]


def test_identical_records_are_unchanged(records):
    result = compare(*records)
    assert result["changes"] == []
    assert result["summary"]["compared_answers"] == 3


def test_same_choice_can_cross_confidence_gate(records):
    before, after = records
    after["ticket-1"]["response"]["answers"]["queue"]["confidence"] = 0.79
    report = compare(before, after, policy={"queue": {"confidence": 0.8}})
    assert kinds(report) == ["threshold_crossed"]
    assert report["changes"][0]["before_side"] == "at_or_above"
    assert report["changes"][0]["after_side"] == "below"


def test_policy_only_change_is_replayed(records):
    report = compare(
        *records,
        policy={"queue": {"confidence": 0.8}},
        candidate_policy={"queue": {"confidence": 0.9}},
    )
    assert kinds(report) == ["threshold_crossed"]
    assert report["notices"][0]["kind"] == "threshold_changed"


def test_equality_is_on_the_upper_side(records):
    records[1]["ticket-1"]["response"]["answers"]["urgent"]["noul"] = 0.9
    report = compare(*records, policy={"urgent": {"threshold": 0.9}})
    assert report["changes"][0]["after_side"] == "at_or_above"


def test_score_threshold_uses_level_position_not_probability(records):
    records[1]["ticket-1"]["response"]["answers"]["severity"]["score"] = 1.5
    report = compare(*records, policy={"severity": {"threshold": 1.5}})
    assert kinds(report) == ["threshold_crossed"]


def test_model_change_is_a_notice_not_a_behavior_change(records):
    records[1]["ticket-1"]["response"]["model"] = "candidate-model"
    report = compare(*records)
    assert not report["changes"]
    assert report["notices"][0]["kind"] == "model_changed"


def test_missing_and_new_cases_do_not_disappear(records):
    before, after = records
    after["ticket-2"] = after.pop("ticket-1")
    after["ticket-2"]["id"] = "ticket-2"
    report = compare(before, after)
    assert kinds(report) == ["case_removed", "case_added"]
    assert report["summary"]["compared_answers"] == 0


def test_state_change_prevents_false_model_comparison(records):
    records[1]["ticket-1"]["state_hash"] = "a" * 64
    report = compare(*records)
    assert kinds(report) == ["state_changed"]
    assert report["summary"]["compared_answers"] == 0


def test_reworded_question_is_visible(records):
    records[1]["ticket-1"]["questions"]["urgent"]["instructions"] = "Is the sender upset?"
    assert kinds(compare(*records)) == ["question_changed"]


def test_reordered_score_levels_are_not_compared_numerically(records):
    row = records[1]["ticket-1"]
    row["questions"]["severity"]["criteria"].reverse()
    row["response"]["answers"]["severity"]["legend"] = {
        "0": "Blocked",
        "1": "Workaround exists",
        "2": "Cosmetic",
    }
    row["response"]["answers"]["severity"]["score"] = 1.8
    report = compare(*records, policy={"severity": {"threshold": 1.5}})
    assert kinds(report) == ["question_changed"]
    assert report["summary"]["compared_answers"] == 2


def test_distribution_can_change_without_score_change(records):
    old = records[0]["ticket-1"]["response"]["answers"]["severity"]
    new = records[1]["ticket-1"]["response"]["answers"]["severity"]
    old.update(score=1.0, probabilities={"0": 0.0, "1": 1.0, "2": 0.0})
    new.update(score=1.0, probabilities={"0": 0.5, "1": 0.0, "2": 0.5})
    report = compare(*records)
    assert kinds(report) == ["distribution_shift"]
    assert report["changes"][0]["distance"] == 1.0


def test_choice_flip_is_reported_even_for_tiny_distribution_shift(records):
    old = records[0]["ticket-1"]["response"]["answers"]["queue"]
    new = records[1]["ticket-1"]["response"]["answers"]["queue"]
    old["probabilities"] = {"billing": 0.51, "support": 0.49}
    new.update(choice="support", probabilities={"billing": 0.49, "support": 0.51})
    assert kinds(compare(*records)) == ["choice_changed"]


def test_tv_boundary_does_not_fail_from_float_roundoff(records):
    records[1]["ticket-1"]["response"]["answers"]["urgent"]["noul"] = 0.69
    assert compare(*records, max_tv=0.2)["changes"] == []


def test_rounded_probability_mass_is_normalized(records):
    row = records[1]["ticket-1"]["response"]["answers"]["queue"]
    row["probabilities"] = {"billing": 0.891, "support": 0.099}
    assert not compare(*records, max_tv=0)["changes"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, -0.1, 1.1, "0.9"])
def test_bad_probabilities_fail_with_a_useful_error(records, value):
    records[1]["ticket-1"]["response"]["answers"]["urgent"]["noul"] = value
    with pytest.raises(RecordError, match="urgent.noul"):
        compare(*records)


@pytest.mark.parametrize(
    "policy,match",
    [
        ({"typo": {"threshold": 0.5}}, "not found"),
        ({"urgent": {"confidence": 0.5}}, "no confidence"),
        ({"queue": {"threshold": 0.5}}, "no numeric threshold"),
        ({"severity": {"threshold": 2.1}}, "finite number"),
        ({"queue": {"confidnce": 0.9}}, "use confidence"),
        ({"queue": {}}, "use confidence"),
    ],
)
def test_invalid_policy_never_silently_passes(records, policy, match):
    with pytest.raises(RecordError, match=match):
        compare(*records, policy=policy)


def test_added_gate_is_visible(records):
    result = compare(*records, candidate_policy={"urgent": {"threshold": 0.9}})
    assert kinds(result) == ["gate_changed"]


def test_missing_answer_is_invalid_not_an_unchanged_result(records):
    del records[1]["ticket-1"]["response"]["answers"]["urgent"]
    with pytest.raises(RecordError, match="match the request"):
        compare(*records)


def test_missing_question_is_a_change_when_record_is_complete(records):
    del records[1]["ticket-1"]["questions"]["urgent"]
    del records[1]["ticket-1"]["response"]["answers"]["urgent"]
    assert kinds(compare(*records)) == ["question_removed"]


def test_record_excludes_state_headers_and_usage_and_is_detached():
    request, response = pair()
    request["headers"] = {"Authorization": "secret"}
    request["state"] = "private customer message"
    response["headers"] = {"Authorization": "secret"}
    record = make_record("ticket", request, response)
    text = json.dumps(record)
    assert "private customer message" not in text
    assert "secret" not in text
    assert "usage" not in text
    response["answers"]["urgent"]["noul"] = 0
    assert record["response"]["answers"]["urgent"]["noul"] == 0.89


def test_state_hash_ignores_object_key_order_but_preserves_array_order():
    request, response = pair()
    request["state"] = {"a": [1, 2], "b": 3}
    first = make_record("one", request, response)
    request["state"] = {"b": 3, "a": [1, 2]}
    assert make_record("one", request, response)["state_hash"] == first["state_hash"]
    request["state"]["a"].reverse()
    assert make_record("one", request, response)["state_hash"] != first["state_hash"]


def test_duplicate_ids_have_file_and_line_context(records, tmp_path):
    path = tmp_path / "records.jsonl"
    line = json.dumps(records[0]["ticket-1"])
    path.write_text(line + "\n" + line + "\n")
    with pytest.raises(RecordError, match=r"records.jsonl:2: duplicate case ID"):
        load_records(path)


@pytest.mark.parametrize(
    "content,match",
    [
        ("\n", "no records"),
        ('{"id":"a","id":"b"}', "duplicate JSON key"),
        ('{"id":', "invalid JSON"),
    ],
)
def test_invalid_jsonl_is_not_a_green_run(tmp_path, content, match):
    path = tmp_path / "records.jsonl"
    path.write_text(content)
    with pytest.raises(RecordError, match=match):
        load_records(path)


def test_comparison_order_is_stable(records):
    before, after = records
    before["z"] = copy.deepcopy(before["ticket-1"])
    before["z"]["id"] = "z"
    after["z"] = copy.deepcopy(before["z"])
    after["z"]["state_hash"] = "a" * 64
    assert compare(before, after) == compare(dict(reversed(list(before.items()))), after)


def cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "jev_diff", *map(str, args)], text=True, capture_output=True
    )


def test_cli_record_compare_and_exit_codes(tmp_path):
    request, response = pair()
    req = tmp_path / "request.json"
    res = tmp_path / "response.json"
    req.write_text(json.dumps(request))
    res.write_text(json.dumps(response))
    recorded = cli("record", "--id", "one", "--request", req, "--response", res)
    assert recorded.returncode == 0, recorded.stderr
    baseline = tmp_path / "baseline.jsonl"
    baseline.write_text(recorded.stdout)
    unchanged = cli("compare", baseline, baseline, "--json")
    assert unchanged.returncode == 0, unchanged.stderr
    assert json.loads(unchanged.stdout)["summary"]["compared_answers"] == 3
    record = json.loads(recorded.stdout)
    record["response"]["answers"]["urgent"]["noul"] = 0.1
    candidate = tmp_path / "candidate.jsonl"
    candidate.write_text(json.dumps(record))
    changed = cli("compare", baseline, candidate, "--json")
    assert changed.returncode == 1
    assert kinds(json.loads(changed.stdout)) == ["distribution_shift"]
    invalid = cli("compare", baseline, tmp_path / "missing.jsonl")
    assert invalid.returncode == 2
    assert "jev-diff:" in invalid.stderr
    assert "Traceback" not in invalid.stderr


def test_cli_does_not_emit_terminal_control_characters(tmp_path):
    request, response = pair()
    before = make_record("\x1b[31mred", request, response)
    after = copy.deepcopy(before)
    after["response"]["answers"]["urgent"]["noul"] = 0.1
    for name, record in (("a", before), ("b", after)):
        (tmp_path / name).write_text(json.dumps(record))
    result = cli("compare", tmp_path / "a", tmp_path / "b")
    assert result.returncode == 1
    assert "\x1b" not in result.stdout
    assert "\\u001b" in result.stdout


def test_many_rounded_choices_are_accepted():
    request, response = pair()
    request["questions"]["queue"]["criteria"] = {str(i): None for i in range(7)}
    response["answers"]["queue"].update(choice="0", probabilities={str(i): 0.14 for i in range(7)})
    row = make_record("rounded", request, response)
    assert not compare({"rounded": row}, {"rounded": row})["changes"]


def test_large_integer_in_probability_is_an_input_error(records):
    records[1]["ticket-1"]["response"]["answers"]["urgent"]["noul"] = 10**400
    with pytest.raises(RecordError, match="finite number"):
        compare(*records)
