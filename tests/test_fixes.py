"""Regression tests for the fixes from the TLA+ audit (C:\\ClaudeWork\\Tools\\audit\\tla\\Autoresearch.tla):
git calls wait out someone else's index.lock, and a resumed run catches up with a kept commit that state.json missed.

    uv run -q --python 3.12 --with pytest pytest -q tests/test_fixes.py
"""
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import driver  # noqa: E402

ID = ["-c", "user.name=t", "-c", "user.email=t@localhost"]


def sh(*a):
    return subprocess.run(["git", *ID, *a], capture_output=True, text=True, check=True).stdout.strip()


def commit(msg, content):
    Path("x.txt").write_text(content)
    sh("add", "-A")
    sh("commit", "-q", "-m", msg)
    return sh("rev-parse", "--short", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sh("init", "-q")
    Path("autoresearch").mkdir()
    Path("autoresearch/config.json").write_text(json.dumps({"editable": ["x.txt"]}))
    base = commit("init", "0")
    monkeypatch.setattr(driver, "log", lambda msg: None)
    return base


def test_git_waits_for_a_held_index_lock(repo, monkeypatch):
    Path("x.txt").write_text("changed")
    lock = Path(".git/index.lock")
    lock.write_text("")
    threading.Timer(1.5, lock.unlink).start()           # someone's `git status` lets go
    driver.git("add", "x.txt")                           # used to raise "index.lock: File exists"
    assert "x.txt" in sh("diff", "--cached", "--name-only")


def test_git_still_fails_if_the_lock_never_goes(repo, monkeypatch):
    monkeypatch.setattr(driver, "GIT_LOCK_WAIT_S", 1)
    Path("x.txt").write_text("changed")
    Path(".git/index.lock").write_text("")
    with pytest.raises(RuntimeError, match="lock"):
        driver.git("add", "x.txt")


def test_resume_catches_up_with_an_unsaved_kept_commit(repo):
    state = {"best": 1.0, "best_commit": repo, "round": 2, "kept": 0, "seen": {}}
    sha = commit("autoresearch r3: better idea (score 1.5)", "1")
    assert driver.catch_up_head(state)
    assert state["best"] == 1.5 and state["best_commit"] == sha and state["round"] == 3
    assert not driver.better(1.4, state["best"], "max", 0.0)   # a worse candidate is no longer kept


def test_resume_takes_the_newest_kept_commit_including_sweeps(repo):
    state = {"best": 1.0, "best_commit": repo, "round": 2, "seen": {}}
    commit("autoresearch r3: idea (score 1.5)", "1")
    sha = commit("autoresearch r3 sweep: lookback=5 (score 1.75)", "2")
    assert driver.catch_up_head(state) and state["best"] == 1.75 and state["best_commit"] == sha


def test_resume_does_nothing_when_state_is_current(repo):
    sha = commit("autoresearch r3: idea (score 1.5)", "1")
    state = {"best": 1.5, "best_commit": sha, "round": 3, "seen": {}}
    assert not driver.catch_up_head(state) and state["best"] == 1.5


def test_resume_ignores_commits_that_are_not_kept_rounds(repo):
    state = {"best": 1.0, "best_commit": repo, "round": 2, "seen": {}}
    commit("config: raise max_rounds", "1")               # e.g. brain-daily-explore's own commit
    assert not driver.catch_up_head(state) and state["best"] == 1.0


def test_resume_does_nothing_if_best_commit_is_not_an_ancestor(repo):
    state = {"best": 1.0, "best_commit": "deadbeef", "round": 2, "seen": {}}
    commit("autoresearch r3: idea (score 1.5)", "1")
    assert not driver.catch_up_head(state) and state["best"] == 1.0


def test_explore_branch_without_a_kept_version_catches_up_its_seed(repo):
    commit("autoresearch branch b2: editable files reset to the baseline", "0b")
    sha = commit("autoresearch r7: seed idea (score -0.25)", "s")
    state = {"best": None, "best_commit": None, "round": 6, "seed_pending": True, "seen": {}}
    assert driver.catch_up_head(state)
    assert state["best"] == -0.25 and state["best_commit"] == sha and state["seed_pending"] is False
