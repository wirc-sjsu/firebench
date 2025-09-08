"""
Dev-only namespace consistency checker.

- Reads a fixed Markdown file to get the list of standard variable names.
- Imports `svn` from `firebench` to get the authoritative list from code.
- Compares both lists and prints differences.
- No argparse, no unit/type checks, no JSON.

Usage:
    in root directory: make check-consistency-namespace
"""

import re
from pathlib import Path

# Docs path
NAMESPACE_DOCS = Path("docs/namespace.md")
_MD_NAME_RE = re.compile(r"-\s*`([^`]+)`")

def get_md_variables(md_path: Path) -> list[str]:
    """Return the list of variable names listed in the Markdown spec."""
    text = md_path.read_text(encoding="utf-8")
    return _MD_NAME_RE.findall(text)

def get_svn_variables() -> list[str]:
    """Return the list of variable names from `firebench.svn`.

    Supports several shapes:
      - Enum class (uses __members__)
      - dict of names
      - list/tuple/set of names
      - module / object with UPPERCASE attributes
    """
    from firebench import svn

    # Enum class (most common)
    members = getattr(svn, "__members__", None)
    if isinstance(members, dict):
        return sorted(members.keys())

    # collect UPPERCASE attribute names on the object/module
    names = [n for n in dir(svn) if n.isupper() and not n.startswith("_")]
    return sorted(set(names))

def check_consistency() -> None:
    md_vars = set(get_md_variables(NAMESPACE_DOCS))
    svn_vars = set(get_svn_variables())

    only_in_docs = sorted(md_vars - svn_vars)
    only_in_svn  = sorted(svn_vars - md_vars)
    common       = sorted(md_vars & svn_vars)

    print("== Namespace Consistency Check ==")
    print(f"Common: {len(common)}")
    print(f"Only in docs (missing from svn): {len(only_in_docs)}")
    for name in only_in_docs:
        print(f"  - {name}")
    print(f"Only in svn (missing from docs): {len(only_in_svn)}")
    for name in only_in_svn:
        print(f"  - {name}")

if __name__ == "__main__":
    check_consistency()
