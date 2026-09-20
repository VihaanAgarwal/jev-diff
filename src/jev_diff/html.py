import base64
import hashlib
import json
import os
import tempfile
from importlib.resources import files
from pathlib import Path

from .records import RecordError


def _records(records):
    return {
        key: {field: record[field] for field in ("id", "state_hash", "questions", "response")}
        for key, record in sorted(records.items())
    }


def render_html(report, before, after, *, policy, candidate_policy, max_tv, labels):
    """Render an already validated comparison with its evidence, without remote assets."""
    assets = files("jev_diff").joinpath("assets")
    script = assets.joinpath("report.js").read_text(encoding="utf-8")
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    payload = (
        json.dumps(
            {
                "report": report,
                "before": _records(before),
                "after": _records(after),
                "policy": policy,
                "candidate_policy": candidate_policy,
                "max_tv": max_tv,
                "labels": labels,
            },
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    template = assets.joinpath("report.html").read_text(encoding="utf-8")
    # Insert data last, so user text can never become a template substitution.
    return (
        template.replace("__SCRIPT_HASH__", digest)
        .replace("__CSS__", assets.joinpath("report.css").read_text(encoding="utf-8"))
        .replace("__JS__", script)
        .replace("__DATA__", payload)
    )


def write_html(path, content, inputs):
    path = Path(path)
    for source in inputs:
        if source is not None and (
            path.resolve() == source.resolve() or (path.exists() and path.samefile(source))
        ):
            raise RecordError("HTML output must not replace an input file")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".jev-diff-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
