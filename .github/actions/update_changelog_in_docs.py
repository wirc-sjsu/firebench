import os


def update_changelog_in_docs():
    """
    Update the documentation changelog file with the content from the root CHANGELOG.md file.

    This function reads the content of the root CHANGELOG.md file and writes it to the
    docs/changelog.md file, adding necessary front matter for the documentation format.
    """
    # Define paths to the source and destination changelog files
    root_changelog_path = os.path.join("CHANGELOG.md")
    docs_changelog_path = os.path.join("docs", "changelog.md")

    # Read the content of CHANGELOG.md
    with open(root_changelog_path, "r") as root_file:
        changelog_content = root_file.read()

    # Front matter for the docs/changelog.md file
    front_matter = """# 12. """

    # Combine front matter and changelog content
    full_changelog_content = front_matter + changelog_content[2:]

    # Write the combined content to docs/changelog.md
    with open(docs_changelog_path, "w") as docs_file:
        docs_file.write(full_changelog_content)


if __name__ == "__main__":
    update_changelog_in_docs()
