"""Fail if any doc or source string tells users to pip-install our package from PyPI.

Saluca does not distribute through PyPI, and a PyPI project that shares a name
with this repo is not ours. Install instructions for our own packages must be a
git install from the saluca-labs GitHub org, for example:

    pip install "<name>[extra] @ git+https://github.com/saluca-labs/<repo>@<ref>"

Usage: python .github/scripts/check_install_docs.py NAME [NAME ...]
Exit status 1 lists every offending line.
"""
import pathlib
import re
import shlex
import subprocess
import sys

INSTALL = re.compile(r"\bpip3?\s+install\b(?P<args>[^`\n]*)")
ORG_GIT = "git+https://github.com/saluca-labs/"


def _norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def offending_args(line, ours):
    bad = []
    for m in INSTALL.finditer(line):
        raw = m.group("args").strip().rstrip(")").strip()
        try:
            args = shlex.split(raw)
        except ValueError:
            args = raw.split()
        for arg in args:
            if arg.startswith("-") or ORG_GIT in arg:
                continue
            name = re.match(r"[A-Za-z0-9][A-Za-z0-9_.-]*", arg)
            if name and _norm(name.group(0)) in ours:
                bad.append(arg)
    return bad


def main(argv):
    ours = {_norm(n) for n in argv[1:]}
    if not ours:
        print("usage: check_install_docs.py NAME [NAME ...]")
        return 2
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    failures = []
    for f in files:
        if not f.endswith((".md", ".rst", ".txt", ".py", ".toml", ".cfg")) or f.startswith(".github/scripts/"):
            continue
        text = pathlib.Path(f).read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            for arg in offending_args(line, ours):
                failures.append(f"{f}:{i}: PyPI-style install of our package: {arg!r}")
    for x in failures:
        print(x)
    if failures:
        print(f"\n{len(failures)} PyPI install instruction(s). Use {ORG_GIT}<repo>@<ref> instead.")
        return 1
    print("OK: no PyPI install instructions for", ", ".join(sorted(ours)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
