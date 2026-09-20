"""Build the public review demo from synthetic decisions, without API calls."""

import copy
import json
from pathlib import Path

from jev_diff import compare, make_record
from jev_diff.html import render_html

ROOT = Path(__file__).resolve().parents[1]
request = {
    "model": "jev-1.13.0",
    "state": "Synthetic support ticket",
    "questions": {
        "queue": {
            "type": "choice",
            "instructions": "Which team should handle this support ticket?",
            "criteria": {"billing": "Payments and refunds", "support": "Product help"},
        },
        "urgent": {"type": "noul", "instructions": "Does this ticket need immediate attention?"},
        "severity": {
            "type": "score",
            "instructions": "How much does the issue prevent the customer from using the product?",
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
            "score": 1.0,
            "confidence": 0.75,
            "legend": {"0": "Cosmetic", "1": "Workaround exists", "2": "Blocked"},
            "probabilities": {"0": 0, "1": 1, "2": 0},
        },
    },
}
policy = {"queue": {"confidence": 0.8}, "urgent": {"threshold": 0.9}}
before = {}
for case_id in (
    "ticket-014",
    "ticket-021",
    "ticket-034",
    "ticket-042",
    "ticket-057",
    "ticket-063",
    "ticket-071",
):
    request["state"] = {"synthetic_case": case_id}
    before[case_id] = make_record(case_id, request, response)
after = copy.deepcopy(before)
after["ticket-014"]["response"]["answers"]["queue"]["confidence"] = 0.79
after["ticket-014"]["response"]["answers"]["urgent"]["noul"] = 0.91
after["ticket-021"]["response"]["answers"]["queue"].update(
    choice="support", probabilities={"billing": 0.1, "support": 0.9}
)
after["ticket-034"]["response"]["answers"]["severity"]["probabilities"] = {
    "0": 0.5,
    "1": 0,
    "2": 0.5,
}
after["ticket-042"]["state_hash"] = "f" * 64
after["ticket-057"]["questions"]["urgent"]["instructions"] = (
    "Is the customer unable to continue working?"
)
del after["ticket-071"]
request["state"] = {"synthetic_case": "ticket-088"}
after["ticket-088"] = make_record("ticket-088", request, response)
folder = ROOT / "examples" / "review"
folder.mkdir(exist_ok=True)
for filename, records in (
    ("synthetic-baseline.jsonl", before),
    ("synthetic-candidate.jsonl", after),
):
    (folder / filename).write_text(
        "".join(json.dumps(record) + "\n" for record in records.values()), encoding="utf-8"
    )
(folder / "policy.json").write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
report = compare(before, after, policy=policy)
html = render_html(
    report,
    before,
    after,
    policy=policy,
    candidate_policy=policy,
    max_tv=0.2,
    labels={"baseline": "synthetic-baseline.jsonl", "candidate": "synthetic-candidate.jsonl"},
)
html = html.replace(
    "<main>",
    '<main><p class="warning" style="margin:0 0 28px">Interactive example. '
    "These decisions are synthetic, not a Jev benchmark. "
    '<a href="https://github.com/VihaanAgarwal/jev-diff">Get jev-diff on GitHub</a>.</p>',
)
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "index.html").write_text(html, encoding="utf-8")
print(json.dumps(report["summary"]))
