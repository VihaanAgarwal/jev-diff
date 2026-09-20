import hashlib
import json
import math
from pathlib import Path


class RecordError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecordError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def read_json(text):
    try:
        return json.loads(text, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        raise RecordError(f"invalid JSON: {exc.msg}") from exc


def canonical(value):
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise RecordError("expected finite JSON values with string object keys") from exc


def _object(value, where):
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise RecordError(f"{where}: expected an object with string keys")
    return value


def _string(value, where):
    if not isinstance(value, str) or not value:
        raise RecordError(f"{where}: expected a nonempty string")


def number(value, where, low=0, high=1):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecordError(f"{where}: expected a number")
    if not low <= value <= high or not math.isfinite(value):
        raise RecordError(f"{where}: expected a finite number in [{low}, {high}]")
    return value


def validate_record(record):
    _object(record, "record")
    if type(record.get("version")) is not int or record["version"] != 1:
        raise RecordError("record.version: expected 1")
    _string(record.get("id"), "record.id")
    digest = record.get("state_hash")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise RecordError("record.state_hash: expected a lowercase SHA-256 digest")
    questions = _object(record.get("questions"), "record.questions")
    if not questions:
        raise RecordError("record.questions: cannot be empty")
    response = _object(record.get("response"), "record.response")
    _string(response.get("model"), "response.model")
    answers = _object(response.get("answers"), "response.answers")
    if answers.keys() != questions.keys():
        raise RecordError("response.answers: question IDs must match the request exactly")
    for name, question in questions.items():
        _string(name, "question ID")
        _object(question, f"question {name!r}")
        kind = question.get("type")
        if kind not in ("choice", "noul", "score"):
            raise RecordError(f"question {name!r}: unknown type {kind!r}")
        if not isinstance(question.get("instructions"), (str, dict, list)):
            raise RecordError(f"question {name!r}: instructions must be text, object, or array")
        answer = _object(answers[name], f"answer {name!r}")
        if answer.get("type") != kind:
            raise RecordError(f"answer {name!r}: type must match question type {kind!r}")
        if kind == "noul":
            number(answer.get("noul"), f"{name}.noul")
            continue
        criteria = question.get("criteria")
        if kind == "choice":
            _object(criteria, f"{name}.criteria")
            if not 1 <= len(criteria) <= 255:
                raise RecordError(f"{name}.criteria: expected 1 to 255 choices")
            keys = set(criteria)
            if not isinstance(answer.get("choice"), str) or answer["choice"] not in keys:
                raise RecordError(f"{name}.choice: not in criteria")
        else:
            if not isinstance(criteria, list) or not 2 <= len(criteria) <= 10:
                raise RecordError(f"{name}.criteria: expected 2 to 10 score levels")
            keys = {str(i) for i in range(len(criteria))}
            number(answer.get("score"), f"{name}.score", high=len(criteria) - 1)
            legend = _object(answer.get("legend"), f"{name}.legend")
            if set(legend) != keys or any(legend[str(i)] != v for i, v in enumerate(criteria)):
                raise RecordError(f"{name}.legend: must match the ordered criteria")
        number(answer.get("confidence"), f"{name}.confidence")
        probabilities = _object(answer.get("probabilities"), f"{name}.probabilities")
        if set(probabilities) != keys:
            raise RecordError(f"{name}.probabilities: must contain exactly the criteria keys")
        for key, value in probabilities.items():
            number(value, f"{name}.probabilities[{key!r}]")
        # Two-decimal rounding accumulates when a Choice has many options.
        values = probabilities.values()
        on_grid = all(abs(value * 100 - round(value * 100)) < 1e-9 for value in values)
        tolerance = max(0.01, 0.005 * len(probabilities)) if on_grid else 0.01
        total = math.fsum(values)
        if total == 0 or abs(total - 1) > tolerance + 1e-9:
            raise RecordError(f"{name}.probabilities: invalid probability mass")
    canonical(record)
    return record


def make_record(case_id, request, response):
    """Keep the decision contract and a state digest; omit raw state and HTTP headers."""
    _object(request, "request")
    _object(response, "response")
    if "state" not in request:
        raise RecordError("request.state: missing")
    _string(request.get("model"), "request.model")
    record = {
        "version": 1,
        "id": case_id,
        "state_hash": hashlib.sha256(canonical(request["state"]).encode()).hexdigest(),
        "questions": request.get("questions"),
        "response": {"model": response.get("model"), "answers": response.get("answers")},
    }
    # Round-trip to detach the record from mutable application objects.
    return validate_record(read_json(canonical(record)))


def load_records(path):
    records = {}
    with Path(path).open(encoding="utf-8") as source:
        for line_no, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                record = validate_record(read_json(line))
                if record["id"] in records:
                    raise RecordError(f"duplicate case ID: {record['id']!r}")
                records[record["id"]] = record
            except RecordError as exc:
                raise RecordError(f"{path}:{line_no}: {exc}") from exc
    if not records:
        raise RecordError(f"{path}: no records")
    return records
