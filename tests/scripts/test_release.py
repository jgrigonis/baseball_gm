# tests/scripts/test_release.py
"""`scripts/release.py` bumps the version, adds a CHANGES.txt entry, commits,
tags and pushes, all against a throwaway repo and remote."""

import subprocess

import pytest

from scripts import release
from scripts.release import ReleaseError

PYPROJECT = """[build-system]
requires = ["setuptools>=61.0"]

[project]
name = "baseball_manager"
version = "0.5.6"

[tool.other]
version = "9.9.9"
"""

CHANGES = """0.5.6
-----

- Move to python 3.14 as base requirement
"""


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    _git(tmp_path, "init", "-q", "-b", "main", str(work))
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "Test")
    (work / "pyproject.toml").write_text(PYPROJECT)
    (work / "CHANGES.txt").write_text(CHANGES)
    _git(work, "add", ".")
    _git(work, "commit", "-q", "-m", "init")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "-q", "-u", "origin", "main")
    return work, remote


@pytest.mark.parametrize("bump, expected", [
    ("patch", "0.5.7"), ("minor", "0.6.0"), ("major", "1.0.0"), ("0.7.2", "0.7.2"),
])
def test_next_version(bump, expected):
    assert release.next_version("0.5.6", bump) == expected


@pytest.mark.parametrize("bump", ["0.5.6", "0.5.5", "huge", "1.0"])
def test_next_version_rejects(bump):
    with pytest.raises(ReleaseError):
        release.next_version("0.5.6", bump)


def test_set_version_only_touches_project_table():
    updated = release.set_version(PYPROJECT, "0.5.7")
    assert release.read_version(updated) == "0.5.7"
    assert 'version = "9.9.9"' in updated


def test_release_commits_tags_and_pushes(repo):
    work, remote = repo
    assert release.release("patch", ["Fix the box score", "Faster sims"], cwd=work) == "0.5.7"

    assert (work / "CHANGES.txt").read_text() == (
        "0.5.7\n-----\n\n- Fix the box score\n- Faster sims\n\n\n" + CHANGES
    )
    assert release.read_version((work / "pyproject.toml").read_text()) == "0.5.7"
    assert _git(remote, "log", "-1", "--format=%s", "main") == "Release 0.5.7"
    assert _git(remote, "cat-file", "-t", "v0.5.7") == "tag"
    assert _git(remote, "tag", "-l", "--format=%(contents:subject)", "v0.5.7") == "version 0.5.7"
    assert _git(remote, "rev-parse", "v0.5.7^{}") == _git(remote, "rev-parse", "main")


def test_dry_run_changes_nothing(repo):
    work, remote = repo
    release.release("minor", ["Notes"], cwd=work, dry_run=True)
    assert (work / "CHANGES.txt").read_text() == CHANGES
    assert _git(work, "status", "--porcelain") == ""
    assert _git(work, "tag") == ""


def test_no_push_keeps_it_local(repo):
    work, remote = repo
    release.release("patch", ["Notes"], cwd=work, push=False)
    assert _git(work, "tag") == "v0.5.7"
    assert _git(remote, "tag") == ""
    assert _git(remote, "log", "-1", "--format=%s", "main") == "init"


def test_declining_confirmation_changes_nothing(repo):
    work, _remote = repo
    assert release.release("patch", ["Notes"], cwd=work, confirm=lambda _s: False) is None
    assert _git(work, "status", "--porcelain") == ""


def test_refuses_dirty_tree(repo):
    work, _remote = repo
    (work / "scratch.txt").write_text("x")
    with pytest.raises(ReleaseError, match="uncommitted"):
        release.release("patch", ["Notes"], cwd=work)


def test_refuses_other_branch(repo):
    work, _remote = repo
    _git(work, "checkout", "-q", "-b", "feature")
    with pytest.raises(ReleaseError, match="releases are cut from main"):
        release.release("patch", ["Notes"], cwd=work)


def test_refuses_unpushed_commits(repo):
    work, _remote = repo
    _git(work, "commit", "-q", "--allow-empty", "-m", "local only")
    with pytest.raises(ReleaseError, match="not in sync"):
        release.release("patch", ["Notes"], cwd=work)


def test_refuses_existing_tag(repo):
    work, _remote = repo
    _git(work, "tag", "v0.5.7")
    with pytest.raises(ReleaseError, match="already exists"):
        release.release("patch", ["Notes"], cwd=work)


def test_needs_notes(repo):
    work, _remote = repo
    with pytest.raises(ReleaseError, match="change note"):
        release.release("patch", ["  "], cwd=work)
