import argparse
import json
import sys
from pathlib import Path

from .compare import compare
from .html import render_html, write_html
from .records import RecordError, load_records, make_record, read_json


def _read(path):
    return read_json(Path(path).read_text(encoding="utf-8"))


def _display(value):
    return json.dumps(value, ensure_ascii=True)


def _render(report):
    summary = report["summary"]
    print(
        f"Compared answers: {summary['compared_answers']} | "
        f"Changes: {summary['changes']} | Changed cases: {summary['changed_cases']}"
    )
    for change in report["changes"]:
        location = _display(change["case"])
        if change["question"] is not None:
            location += "/" + _display(change["question"])
        detail = ""
        if change["kind"] == "threshold_crossed":
            detail = (
                f" {change['field']}: {change['before']:g} -> {change['after']:g}"
                f" ({change['before_side']} -> {change['after_side']};"
                f" gate {change['old_threshold']:g} -> {change['new_threshold']:g})"
            )
        elif change["kind"] == "choice_changed":
            detail = f" {_display(change['before'])} -> {_display(change['after'])}"
        elif change["kind"] == "distribution_shift":
            detail = f" TV={change['distance']:.3f} > {change['limit']:g}"
        print(f"  {location}  {change['kind']}{detail}")
    for notice in report["notices"]:
        print(f"  note: {_display(notice)}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare saved Jev decisions offline.")
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record", help="Pack a raw HTTP request/response pair as JSONL")
    record.add_argument("--id", required=True, help="Stable ID for this test case")
    record.add_argument("--request", required=True, type=Path)
    record.add_argument("--response", required=True, type=Path)
    diff = commands.add_parser("compare", help="Compare two JSONL files by case ID")
    diff.add_argument("baseline", type=Path)
    diff.add_argument("candidate", type=Path)
    diff.add_argument("--policy", type=Path, help="Per-question confidence/threshold gates")
    diff.add_argument("--candidate-policy", type=Path, help="Changed policy; defaults to --policy")
    diff.add_argument("--max-tv", type=float, default=0.2, help="Maximum distribution shift (0..1)")
    diff.add_argument("--json", action="store_true", help="Write a machine-readable report")
    diff.add_argument("--html", type=Path, help="Also save an interactive, offline HTML report")
    args = parser.parse_args(argv)
    try:
        if args.command == "record":
            result = make_record(args.id, _read(args.request), _read(args.response))
            print(json.dumps(result, ensure_ascii=True, allow_nan=False))
            return 0
        before, after = load_records(args.baseline), load_records(args.candidate)
        policy = _read(args.policy) if args.policy else {}
        candidate_policy = _read(args.candidate_policy) if args.candidate_policy else policy
        options = dict(policy=policy, candidate_policy=candidate_policy, max_tv=args.max_tv)
        result = compare(before, after, **options)
        if args.html:
            content = render_html(
                result,
                before,
                after,
                **options,
                labels={"baseline": args.baseline.name, "candidate": args.candidate.name},
            )
            write_html(
                args.html,
                content,
                (args.baseline, args.candidate, args.policy, args.candidate_policy),
            )
            print(f"HTML report: {_display(str(args.html))}", file=sys.stderr)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))
        else:
            _render(result)
        return 1 if result["changes"] else 0
    except (RecordError, OSError, UnicodeError) as exc:
        print(f"jev-diff: {ascii(str(exc))[1:-1]}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
