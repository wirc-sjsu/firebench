import os
from pathlib import Path

PACKAGE_ROOT = Path("src/firebench")
DOCS_API = Path("docs/api")
MODULE_PREFIX = "firebench"

DOCS_API.mkdir(parents=True, exist_ok=True)


def relative_module_path(py_path: Path) -> str:
    parts = py_path.with_suffix("").relative_to(PACKAGE_ROOT).parts
    return ".".join((MODULE_PREFIX,) + parts)


def generate_module_block(module: str) -> str:
    return f""".. automodule:: {module}
   :members:
   :undoc-members:
   :show-inheritance:
"""


def write_api_file(group: str, py_files: list[Path]):
    filename = DOCS_API / f"{group}.rst"
    with filename.open("w") as f:
        f.write(f"{MODULE_PREFIX}.{group}\n")
        f.write("=" * (len(MODULE_PREFIX) + len(group) + 1))
        f.write("\n\n")
        for py_file in sorted(py_files):
            module = relative_module_path(py_file)
            f.write(generate_module_block(module))
            f.write("\n")
    print(f"Wrote {filename}")


def main():
    grouped = {}
    for root, dirs, files in os.walk(PACKAGE_ROOT):
        if "__pycache__" in root:
            continue
        py_files = [f for f in files if f.endswith(".py") and f != "__init__.py" and not f.startswith("_")]
        if not py_files:
            continue
        rel_parts = Path(root).relative_to(PACKAGE_ROOT).parts
        if not rel_parts:
            continue  # skip root
        group = rel_parts[0]
        grouped.setdefault(group, []).extend(Path(root) / f for f in py_files)

    # Write individual group files
    for group, paths in grouped.items():
        write_api_file(group, paths)

    # Write API index.rst
    index_file = DOCS_API / "index.rst"
    with index_file.open("w") as f:
        f.write("API Reference\n")
        f.write("=============\n\n")
        f.write(".. toctree::\n")
        f.write("   :maxdepth: 1\n\n")
        for group in sorted(grouped):
            f.write(f"   {group}.rst\n")
    print(f"Wrote {index_file}")


if __name__ == "__main__":
    main()
