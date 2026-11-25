"""Layer 6 of the commit gate: security/security_diff_review.py and its caller,
layer_6_ai_review() in security/pre_commit_hook.py. subprocess.run is replaced
by a stub that answers as the reviewer CLI does, so no model is called."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

SECURITY_DIR = Path(__file__).resolve().parents[1] / "security"
DIFF = "".join(f"+line {i}\n" for i in range(25))  # over the 20-line minimum
HIGH = {"severity": "High", "description": "stub finding", "file": "a.py", "line": "1"}
MEDIUM = {"severity": "Medium", "description": "stub finding", "file": "a.py", "line": "2"}


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SECURITY_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StubCLI:
    """Stands in for subprocess.run and records each call. codex writes its
    answer to the -o file; claude prints it as the result of a JSON object."""

    def __init__(self, answer: str, returncode: int = 0) -> None:
        self.answer = answer
        self.returncode = returncode
        self.calls: list[dict] = []

    def __call__(self, cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        workdir = Path(kwargs["cwd"])
        self.calls.append({"cmd": cmd, "input": kwargs["input"], "workdir": workdir, "files": os.listdir(workdir)})
        if self.returncode != 0:
            return subprocess.CompletedProcess(cmd, self.returncode, stdout="", stderr="stub failure")
        if Path(cmd[0]).name == "codex":
            Path(cmd[cmd.index("-o") + 1]).write_text(self.answer, encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        result = {"type": "result", "subtype": "success", "is_error": False, "result": self.answer}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(result), stderr="")


@pytest.fixture
def review(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.delenv("SECURITY_DIFF_REVIEWERS", raising=False)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    module = _load("security_diff_review")
    monkeypatch.setattr(module, "get_staged_diff", lambda: DIFF)
    monkeypatch.setattr(module, "_which", lambda name: f"/opt/stub/bin/{name}")
    return module


def _stub(monkeypatch: pytest.MonkeyPatch, answer: str, returncode: int = 0) -> StubCLI:
    stub = StubCLI(answer, returncode)
    monkeypatch.setattr(subprocess, "run", stub)
    return stub


def _exit_code(module: ModuleType) -> object:
    with pytest.raises(SystemExit) as exc_info:
        module.main()
    return exc_info.value.code


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, "claude"),
        ({"CLAUDECODE": "1"}, "astra"),
        ({"SECURITY_DIFF_REVIEWERS": "claude", "CLAUDECODE": "1"}, "claude"),
        ({"SECURITY_DIFF_REVIEWERS": " Astra "}, "astra"),
    ],
)
def test_reviewer_choice(review, monkeypatch, env, expected):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert review.choose_reviewer() == expected
    assert _load("pre_commit_hook")._ai_reviewer() == expected  # the hook's banner names the same reviewer


def test_unknown_reviewer_name_warns_and_skips(review, monkeypatch, capsys):
    monkeypatch.setenv("SECURITY_DIFF_REVIEWERS", "gemini")
    stub = _stub(monkeypatch, json.dumps({"findings": [HIGH]}))
    assert _exit_code(review) == 2
    assert "WARN: SECURITY_DIFF_REVIEWERS='gemini' is not astra or claude" in capsys.readouterr().err
    assert stub.calls == []


@pytest.mark.parametrize("reviewer", ["astra", "claude"])
@pytest.mark.parametrize("severity", ["High", "CRITICAL"])
def test_critical_or_high_finding_blocks(review, monkeypatch, capsys, reviewer, severity):
    monkeypatch.setenv("SECURITY_DIFF_REVIEWERS", reviewer)
    _stub(monkeypatch, json.dumps({"findings": [MEDIUM, {**HIGH, "severity": severity}]}))
    assert _exit_code(review) == 1
    out = capsys.readouterr().out
    assert "] a.py:1 — stub finding" in out
    assert "1 Critical/High finding(s) — commit blocked." in out


@pytest.mark.parametrize("reviewer", ["astra", "claude"])
@pytest.mark.parametrize(
    ("findings", "summary"),
    [([], "No security findings."), ([MEDIUM], "1 finding(s), none Critical/High — passing.")],
)
def test_answer_without_critical_or_high_passes(review, monkeypatch, capsys, reviewer, findings, summary):
    monkeypatch.setenv("SECURITY_DIFF_REVIEWERS", reviewer)
    _stub(monkeypatch, json.dumps({"findings": findings}))
    assert _exit_code(review) == 0
    assert summary in capsys.readouterr().out


def test_missing_cli_warns_and_skips(review, monkeypatch, capsys):
    monkeypatch.setattr(review, "_which", lambda name: None)
    stub = _stub(monkeypatch, json.dumps({"findings": [HIGH]}))
    assert _exit_code(review) == 2
    assert "WARN: Claude Opus (claude-opus-5-5) review unavailable (claude CLI not found)" in capsys.readouterr().err
    assert stub.calls == []


def _time_out(cmd, **kwargs):
    raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])


@pytest.mark.parametrize("failure", ["exit 1", "timeout", "not json"])
def test_failed_review_warns_and_skips(review, monkeypatch, capsys, failure):
    monkeypatch.setenv("CLAUDECODE", "1")
    if failure == "exit 1":
        _stub(monkeypatch, "", returncode=1)
    elif failure == "timeout":
        monkeypatch.setattr(subprocess, "run", _time_out)
    else:
        _stub(monkeypatch, "not json")
    assert _exit_code(review) == 2
    assert capsys.readouterr().err.startswith("WARN: Astra (gpt-6.2-astra) ")


def test_astra_runs_codex_read_only_in_an_empty_directory(review, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    stub = _stub(monkeypatch, json.dumps({"findings": []}))
    assert _exit_code(review) == 0
    (call,) = stub.calls
    cmd = call["cmd"]
    assert cmd[:2] == ["/opt/stub/bin/codex", "exec"] and cmd[-1] == "-"
    assert {"--json", "--ephemeral", "--skip-git-repo-check", 'model_reasoning_effort="medium"'} <= set(cmd)
    for flag, value in [("-s", "read-only"), ("-m", "gpt-6.2-astra"), ("-C", str(call["workdir"]))]:
        assert cmd[cmd.index(flag) + 1] == value
    assert call["files"] == []  # the CLI starts in an empty directory
    assert not call["workdir"].exists()  # which is removed afterwards
    assert review.SECURITY_PROMPT in call["input"] and DIFF in call["input"]


def test_claude_runs_opus_without_tools(review, monkeypatch):
    stub = _stub(monkeypatch, json.dumps({"findings": []}))
    assert _exit_code(review) == 0
    (call,) = stub.calls
    cmd = call["cmd"]
    assert cmd[:2] == ["/opt/stub/bin/claude", "-p"]
    expected = [
        ("--output-format", "json"),
        ("--model", "claude-opus-5-5"),
        ("--effort", "low"),
        ("--tools", ""),
        ("--system-prompt", review.SECURITY_PROMPT),
    ]
    for flag, value in expected:
        assert cmd[cmd.index(flag) + 1] == value
    assert DIFF in call["input"]


@pytest.mark.parametrize(("returncode", "passes"), [(0, True), (1, False), (2, True)])
def test_hook_layer_6_blocks_only_on_exit_1(monkeypatch, capsys, returncode, passes):
    monkeypatch.delenv("SECURITY_DIFF_REVIEWERS", raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")
    gate = _load("pre_commit_hook")
    review = _load("security_diff_review")
    timeouts = []

    def run_review(cmd, timeout=120):
        timeouts.append(timeout)
        return subprocess.CompletedProcess(cmd, returncode, stdout="  [High] a.py:1 — stub finding", stderr="WARN: stub")

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=DIFF, stderr=""))
    monkeypatch.setattr(gate, "_run", run_review)
    assert gate.layer_6_ai_review() is passes
    out = capsys.readouterr().out
    assert "Layer 6: AI Logic Validation (Astra)" in out
    assert ("WARN: stub" in out) is (returncode == 2)
    assert timeouts == [gate.AI_REVIEW_TIMEOUT_S] and gate.AI_REVIEW_TIMEOUT_S > review.TIMEOUT_S
