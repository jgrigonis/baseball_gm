# scripts/release.py

"""Cut a release: bump the version, record it in CHANGES.txt, commit, tag, push.

    python scripts/release.py patch -m "Fix the box score" -m "Faster sims"
    python scripts/release.py minor            # prompts for the change notes
    python scripts/release.py 0.6.0 --dry-run  # show what would happen

The new version goes into pyproject.toml and on top of CHANGES.txt, both are
committed as "Release X.Y.Z" and pushed, then an annotated tag vX.Y.Z is
created and pushed. Run it from a clean, up to date main branch.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_BRANCH = "main"
REMOTE = "origin"

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
# The version line inside [project], not one in some other table.
PYPROJECT_VERSION_RE = re.compile(
    r'(^\[project\]\s*$.*?^version\s*=\s*")([^"]+)(")', re.MULTILINE | re.DOTALL
)


class ReleaseError(Exception):
    pass


def read_version(pyproject_text):
    match = PYPROJECT_VERSION_RE.search(pyproject_text)
    if not match:
        raise ReleaseError("No version found in the [project] table of pyproject.toml")
    return match.group(2)


def set_version(pyproject_text, version):
    if not PYPROJECT_VERSION_RE.search(pyproject_text):
        raise ReleaseError("No version found in the [project] table of pyproject.toml")
    return PYPROJECT_VERSION_RE.sub(rf"\g<1>{version}\g<3>", pyproject_text, count=1)


def next_version(current, bump):
    """`bump` is patch, minor, major, or an explicit X.Y.Z."""
    if VERSION_RE.match(bump):
        new = bump
    elif bump in ("patch", "minor", "major"):
        if not VERSION_RE.match(current):
            raise ReleaseError(f"Current version {current!r} is not X.Y.Z")
        major, minor, patch = (int(part) for part in current.split("."))
        if bump == "major":
            new = f"{major + 1}.0.0"
        elif bump == "minor":
            new = f"{major}.{minor + 1}.0"
        else:
            new = f"{major}.{minor}.{patch + 1}"
    else:
        raise ReleaseError(f"Version must be patch, minor, major or X.Y.Z, not {bump!r}")

    if VERSION_RE.match(current) and _key(new) <= _key(current):
        raise ReleaseError(f"New version {new} is not newer than {current}")
    return new


def _key(version):
    return tuple(int(part) for part in version.split("."))


def changes_entry(version, notes):
    lines = [version, "-" * len(version), ""]
    lines += [f"- {note}" for note in notes]
    return "\n".join(lines) + "\n\n\n"


def add_changes_entry(changes_text, version, notes):
    if re.search(rf"^{re.escape(version)}$", changes_text, re.MULTILINE):
        raise ReleaseError(f"CHANGES.txt already has an entry for {version}")
    return changes_entry(version, notes) + changes_text


def prompt_for_notes():
    print("Enter the change notes, one per line. A blank line finishes.")
    notes = []
    while True:
        try:
            line = input("- ").strip()
        except EOFError:
            break
        if not line:
            break
        notes.append(line)
    return notes


def git(*args, cwd=REPO_ROOT):
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def check_repo(version, cwd=REPO_ROOT, branch=RELEASE_BRANCH, remote=REMOTE):
    """Refuse to release from anywhere but a clean main that matches the remote."""
    current_branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
    if current_branch != branch:
        raise ReleaseError(f"On branch {current_branch}, releases are cut from {branch}")
    if git("status", "--porcelain", cwd=cwd):
        raise ReleaseError("Working tree has uncommitted changes")

    git("fetch", "--tags", remote, branch, cwd=cwd)
    local = git("rev-parse", "HEAD", cwd=cwd)
    upstream = git("rev-parse", f"{remote}/{branch}", cwd=cwd)
    if local != upstream:
        raise ReleaseError(f"{branch} is not in sync with {remote}/{branch}; pull or push first")

    tag = f"v{version}"
    if git("tag", "--list", tag, cwd=cwd):
        raise ReleaseError(f"Tag {tag} already exists")


def release(bump, notes, cwd=REPO_ROOT, dry_run=False, push=True,
            branch=RELEASE_BRANCH, remote=REMOTE, confirm=None):
    """Do the release and return the new version.

    `confirm` is called with a summary before anything changes; returning False
    stops the release.
    """
    pyproject = cwd / "pyproject.toml"
    changes = cwd / "CHANGES.txt"

    pyproject_text = pyproject.read_text()
    current = read_version(pyproject_text)
    version = next_version(current, bump)
    notes = [note.strip() for note in notes if note.strip()]
    if not notes:
        raise ReleaseError("At least one change note is needed for CHANGES.txt")

    check_repo(version, cwd=cwd, branch=branch, remote=remote)

    new_pyproject = set_version(pyproject_text, version)
    new_changes = add_changes_entry(changes.read_text(), version, notes)
    tag = f"v{version}"

    summary = (
        f"Release {current} -> {version}\n\n"
        f"CHANGES.txt entry:\n\n{changes_entry(version, notes).rstrip()}\n\n"
        f"Commit \"Release {version}\" and tag {tag} on {branch}"
        + (f", then push both to {remote}." if push else " (not pushed).")
    )
    print(summary)
    if dry_run:
        print("\nDry run: nothing changed.")
        return version
    if confirm is not None and not confirm(summary):
        print("Stopped: nothing changed.")
        return None

    pyproject.write_text(new_pyproject)
    changes.write_text(new_changes)
    git("add", "pyproject.toml", "CHANGES.txt", cwd=cwd)
    git("commit", "-m", f"Release {version}", cwd=cwd)
    git("tag", "-a", tag, "-m", f"version {version}", cwd=cwd)
    if push:
        git("push", remote, branch, cwd=cwd)
        git("push", remote, tag, cwd=cwd)
        print(f"\nReleased {version} and pushed {tag}.")
    else:
        print(f"\nCommitted and tagged {tag} locally. Push with:\n"
              f"  git push {remote} {branch} && git push {remote} {tag}")
    return version


def _ask(_summary):
    return input("\nGo ahead? [y/N] ").strip().lower() in ("y", "yes")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("version", help="patch, minor, major, or an explicit X.Y.Z")
    parser.add_argument("-m", "--note", action="append", default=[],
                        help="A CHANGES.txt line; repeat for more. Prompts when left out.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without changing anything")
    parser.add_argument("--no-push", action="store_true",
                        help="Commit and tag locally but don't push")
    parser.add_argument("-y", "--yes", action="store_true", help="Don't ask before releasing")
    args = parser.parse_args(argv)

    try:
        # Catch a bad version before asking for notes.
        next_version(read_version((REPO_ROOT / "pyproject.toml").read_text()), args.version)
        notes = args.note or prompt_for_notes()
        release(args.version, notes, dry_run=args.dry_run, push=not args.no_push,
                confirm=None if args.yes else _ask)
    except ReleaseError as exc:
        print(f"release: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
