"""Regenerate illustrative fixtures. These are not recorded Jev measurements."""

import copy
import json
from pathlib import Path

from jev_diff import make_record

HERE = Path(__file__).parent
request = {
    "model": "jev-1.13.0",
    "state": "I was charged twice for the same order.",
    "questions": {
        "queue": {
            "type": "choice",
            "instructions": "Which team handles this ticket?",
            "criteria": {"billing": "Charges and refunds", "support": "Product help"},
        },
        "urgent": {"type": "noul", "instructions": "Does this need immediate attention?"},
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
    },
}
before = make_record("ticket-001", request, response)
after = copy.deepcopy(before)
after["response"]["answers"]["queue"]["confidence"] = 0.79
after["response"]["answers"]["urgent"]["noul"] = 0.91
for name, record in (("baseline", before), ("candidate", after)):
    (HERE / f"{name}.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
(HERE / "policy.json").write_text(
    json.dumps(
        {
            "queue": {"confidence": 0.8},
            "urgent": {"threshold": 0.9},
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
