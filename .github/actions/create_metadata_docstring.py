import textwrap
import sys

# Import your own modules here
from firebench import ureg, svn
from firebench.tools import ParameterType


def format_metadata_bulleted_list(metadata: dict) -> str:
    """Format the metadata dictionary into a nested bullet list."""
    doc = []
    for key, meta in metadata.items():
        std_name = getattr(meta["std_name"], "name", str(meta["std_name"]))
        units = str(meta["units"])
        range_ = f"{meta['range'][0]} to {meta['range'][1]}"
        ptype = meta["type"].name if hasattr(meta["type"], "name") else str(meta["type"])
        default = meta.get("default", None)

        entry = [
            f"- ``{key}``",
            f"    - Standard name: ``{std_name}``",
            f"    - Units: ``{units}``",
            f"    - Range: ``{range_}``",
            f"    - Type: ``{ptype}``",
        ]
        if default is not None:
            entry.append(f"    - Default: ``{default}``")

        doc.append("\n".join(entry))

    return textwrap.indent("\n\n".join(doc), prefix="    ")


def main():
    print(
        "📦 Paste your metadata dictionary using real Python objects (e.g., ureg.meter, ParameterType.input)."
    )
    print("⌨️  End input with Ctrl-D (Linux/macOS) or Ctrl-Z (Windows) + Enter.\n")

    try:
        user_input = sys.stdin.read()
    except EOFError:
        print("❌ No input received.")
        return

    # Create a safe context with only allowed symbols
    context = {
        "ureg": ureg,
        "ParameterType": ParameterType,
        "svn": svn,
        "np": __import__("numpy"),
        "float": float,
    }

    try:
        metadata = eval(user_input, {"__builtins__": {}}, context)
    except Exception as e:
        print(f"❌ Could not evaluate dictionary: {e}")
        return

    print("\n✅ Generated docstring:\n")
    print("    Metadata\n    --------")
    print("    The model uses the following fuel parameters:\n")
    print(format_metadata_bulleted_list(metadata))


if __name__ == "__main__":
    main()
