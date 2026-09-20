import base64
import copy
import hashlib
import json
from html.parser import HTMLParser

import pytest
from test_diff import cli, pair

from jev_diff import make_record


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.scripts = []
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.current = {"attrs": dict(attrs), "text": ""}
            self.scripts.append(self.current)

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data

    def handle_endtag(self, tag):
        if tag == "script":
            self.current = None

    @property
    def payload(self):
        return json.loads(next(s["text"] for s in self.scripts if s["attrs"].get("id") == "data"))


@pytest.fixture
def files(tmp_path):
    before = make_record("ticket-1", *pair())
    after = copy.deepcopy(before)
    after["response"]["answers"]["queue"]["confidence"] = 0.79
    paths = [tmp_path / name for name in ("baseline.jsonl", "candidate.jsonl", "policy.json")]
    for path, value in zip(paths, (before, after, {"queue": {"confidence": 0.8}}), strict=True):
        path.write_text(json.dumps(value))
    return paths


def test_html_and_json_share_the_same_comparison(files, tmp_path):
    before, after, policy = files
    output = tmp_path / "report.html"
    result = cli("compare", before, after, "--policy", policy, "--html", output, "--json")
    assert result.returncode == 1, result.stderr
    payload = Document(output.read_text()).payload
    assert payload["report"] == json.loads(result.stdout)
    assert payload["policy"] == payload["candidate_policy"] == {"queue": {"confidence": 0.8}}
    assert payload["before"]["ticket-1"]["response"]["answers"]["queue"]["confidence"] == 0.81
    assert payload["after"]["ticket-1"]["response"]["answers"]["queue"]["confidence"] == 0.79


def test_html_embeds_hostile_text_as_data_and_omits_extra_record_fields(files, tmp_path):
    before, _, _ = files
    record = json.loads(before.read_text())
    hostile = '</script><script>alert("unsafe")</script><img src=x onerror=alert(1)>'
    record["questions"]["queue"]["instructions"] = hostile
    record["raw_state"] = "private_extra_field"
    before.write_text(json.dumps(record))
    output = tmp_path / "report.html"
    result = cli("compare", before, before, "--html", output)
    assert result.returncode == 0, result.stderr
    html = output.read_text()
    document = Document(html)
    assert len(document.scripts) == 2
    assert hostile not in html
    assert "private_extra_field" not in html
    assert document.payload["before"]["ticket-1"]["questions"]["queue"]["instructions"] == hostile
    assert 'http-equiv="Content-Security-Policy"' in html
    assert "connect-src 'none'" in html


def test_policy_only_change_is_preserved_in_report(files, tmp_path):
    before, _, policy = files
    candidate_policy = tmp_path / "candidate-policy.json"
    candidate_policy.write_text('{"queue":{"confidence":0.9}}')
    output = tmp_path / "report.html"
    result = cli(
        "compare",
        before,
        before,
        "--policy",
        policy,
        "--candidate-policy",
        candidate_policy,
        "--html",
        output,
    )
    assert result.returncode == 1, result.stderr
    payload = Document(output.read_text()).payload
    assert payload["candidate_policy"] == {"queue": {"confidence": 0.9}}
    assert payload["report"]["changes"][0]["kind"] == "threshold_crossed"


@pytest.mark.parametrize("target", [0, 1, 2])
def test_html_output_cannot_overwrite_inputs(files, target):
    originals = [path.read_bytes() for path in files]
    result = cli("compare", *files[:2], "--policy", files[2], "--html", files[target])
    assert result.returncode == 2
    assert "input" in result.stderr
    assert [path.read_bytes() for path in files] == originals
    assert result.stdout == ""


def test_html_output_cannot_overwrite_an_input_through_a_link(files, tmp_path):
    alias = tmp_path / "alias.html"
    alias.symlink_to(files[0])
    result = cli("compare", *files[:2], "--html", alias)
    assert result.returncode == 2
    assert "input" in result.stderr


def test_html_output_cannot_replace_a_hard_link_to_an_input(files, tmp_path):
    alias = tmp_path / "alias.html"
    alias.hardlink_to(files[0])
    original = files[0].read_bytes()
    result = cli("compare", *files[:2], "--html", alias)
    assert result.returncode == 2
    assert "input" in result.stderr
    assert files[0].read_bytes() == alias.read_bytes() == original


def test_report_is_deterministic_and_csp_matches_the_bundled_script(files, tmp_path):
    first, second = tmp_path / "first.html", tmp_path / "second.html"
    for output in (first, second):
        result = cli("compare", *files[:2], "--html", output)
        assert result.returncode == 0, result.stderr
    assert first.read_bytes() == second.read_bytes()
    html = first.read_text()
    script = Document(html).scripts[-1]["text"]
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert f"script-src 'sha256-{digest}'" in html
    assert all("src" not in script["attrs"] for script in Document(html).scripts)


def test_invalid_input_preserves_existing_report(files, tmp_path):
    output = tmp_path / "report.html"
    output.write_text("existing report")
    files[1].write_text("broken")
    result = cli("compare", *files[:2], "--html", output)
    assert result.returncode == 2
    assert result.stdout == ""
    assert output.read_text() == "existing report"
    assert "invalid JSON" in result.stderr


def test_unwritable_report_is_an_input_error_not_a_partial_success(files, tmp_path):
    result = cli("compare", *files[:2], "--html", tmp_path / "missing" / "report.html", "--json")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    assert "No such file or directory" in result.stderr
