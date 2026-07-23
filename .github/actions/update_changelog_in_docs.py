from pathlib import Path


def update_changelog_in_docs():
    """
    Update the documentation changelog file with the content from the root CHANGELOG.md file.

    This function reads the content of the root CHANGELOG.md file and writes it to the
    docs/changelog.md file, adding necessary front matter for the documentation format.
    """
    root_changelog_path = Path("CHANGELOG.md")
    docs_changelog_path = Path("docs/changelog.md")
    docs_changelog_path.write_text(root_changelog_path.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    update_changelog_in_docs()
