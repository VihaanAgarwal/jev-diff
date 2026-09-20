import math

from .records import RecordError, canonical, number, validate_record


def _policy(policy, records):
    if not isinstance(policy, dict):
        raise RecordError("policy must be an object keyed by question ID")
    questions = {}
    for record in records.values():
        for name, question in record["questions"].items():
            questions.setdefault(name, []).append(question)
    for name, gates in policy.items():
        if name not in questions:
            raise RecordError(f"policy {name!r}: question not found in records")
        if not isinstance(gates, dict) or not gates or set(gates) - {"confidence", "threshold"}:
            raise RecordError(f"policy {name!r}: use confidence and/or threshold")
        for question in questions[name]:
            kind = question["type"]
            if "confidence" in gates:
                if kind == "noul":
                    raise RecordError(f"policy {name!r}: Noul has no confidence field")
                number(gates["confidence"], f"policy {name!r}.confidence")
            if "threshold" in gates:
                if kind == "choice":
                    raise RecordError(f"policy {name!r}: Choice has no numeric threshold")
                maximum = 1 if kind == "noul" else len(question["criteria"]) - 1
                number(gates["threshold"], f"policy {name!r}.threshold", high=maximum)
    return policy


def _side(answer, field, threshold):
    return "at_or_above" if answer[field] >= threshold else "below"


def _tv(before, after):
    total_before = math.fsum(before.values())
    total_after = math.fsum(after.values())
    return math.fsum(abs(before[k] / total_before - after[k] / total_after) for k in before) / 2


def compare(before, after, *, policy=None, candidate_policy=None, max_tv=0.2):
    """Compare case-ID maps. This measures changes, not correctness or calibration."""
    number(max_tv, "max_tv")
    for label, records in (("baseline", before), ("candidate", after)):
        if not isinstance(records, dict) or not records:
            raise RecordError(f"{label}: expected a nonempty map of case IDs to records")
        for case_id, record in records.items():
            validate_record(record)
            if case_id != record["id"]:
                raise RecordError(f"{label}: map key does not match record ID")
    old_policy = _policy({} if policy is None else policy, before)
    new_policy = _policy(old_policy if candidate_policy is None else candidate_policy, after)
    changes = []
    notices = []
    compared = 0

    def add(kind, case_id, question=None, **details):
        changes.append({"kind": kind, "case": case_id, "question": question, **details})

    for case_id in sorted(before.keys() | after.keys()):
        if case_id not in before:
            add("case_added", case_id)
            continue
        if case_id not in after:
            add("case_removed", case_id)
            continue
        left, right = before[case_id], after[case_id]
        if left["response"]["model"] != right["response"]["model"]:
            notices.append(
                {
                    "kind": "model_changed",
                    "case": case_id,
                    "before": left["response"]["model"],
                    "after": right["response"]["model"],
                }
            )
        if left["state_hash"] != right["state_hash"]:
            add("state_changed", case_id)
            continue
        old_questions, new_questions = left["questions"], right["questions"]
        for name in sorted(old_questions.keys() | new_questions.keys()):
            if name not in old_questions:
                add("question_added", case_id, name)
                continue
            if name not in new_questions:
                add("question_removed", case_id, name)
                continue
            old_question, new_question = old_questions[name], new_questions[name]
            if canonical(old_question) != canonical(new_question):
                add("question_changed", case_id, name)
            if old_question["type"] != new_question["type"] or canonical(
                old_question.get("criteria")
            ) != canonical(new_question.get("criteria")):
                # Changed labels or score levels no longer describe the same answer space.
                continue
            compared += 1
            old = left["response"]["answers"][name]
            new = right["response"]["answers"][name]
            kind = old["type"]
            if kind == "choice" and old["choice"] != new["choice"]:
                add("choice_changed", case_id, name, before=old["choice"], after=new["choice"])
            if kind == "noul":
                distance = abs(old["noul"] - new["noul"])
            else:
                distance = _tv(old["probabilities"], new["probabilities"])
            if distance > max_tv and not math.isclose(distance, max_tv, abs_tol=1e-12):
                add("distribution_shift", case_id, name, distance=distance, limit=max_tv)
            old_gates = old_policy.get(name, {})
            new_gates = new_policy.get(name, {})
            for gate in sorted(old_gates.keys() | new_gates.keys()):
                if gate not in old_gates or gate not in new_gates:
                    add(
                        "gate_changed",
                        case_id,
                        name,
                        gate=gate,
                        before=old_gates.get(gate),
                        after=new_gates.get(gate),
                    )
                    continue
                field = "confidence" if gate == "confidence" else kind
                a = _side(old, field, old_gates[gate])
                b = _side(new, field, new_gates[gate])
                if old_gates[gate] != new_gates[gate]:
                    notices.append(
                        {
                            "kind": "threshold_changed",
                            "case": case_id,
                            "question": name,
                            "gate": gate,
                            "before": old_gates[gate],
                            "after": new_gates[gate],
                        }
                    )
                if a != b:
                    add(
                        "threshold_crossed",
                        case_id,
                        name,
                        field=field,
                        before=old[field],
                        after=new[field],
                        before_side=a,
                        after_side=b,
                        old_threshold=old_gates[gate],
                        new_threshold=new_gates[gate],
                    )
    return {
        "version": 1,
        "summary": {
            "baseline_cases": len(before),
            "candidate_cases": len(after),
            "compared_answers": compared,
            "changes": len(changes),
            "changed_cases": len({c["case"] for c in changes}),
        },
        "changes": changes,
        "notices": notices,
    }
