import re
import subprocess
import argparse

def run_pylint():
    # Run pylint with the configuration file
    result = subprocess.run(['pylint', 'src/firebench', '--rcfile=.pylintrc'], capture_output=True, text=True)
    output = result.stdout

    # Extract pylint score
    match = re.search(r'Your code has been rated at ([\d\.]+)/10', output)
    if match:
        score = float(match.group(1))
    else:
        raise ValueError("Unable to extract pylint score")

    # Determine badge color based on score
    if score < 5:
        color = 'red'
    elif score < 7:
        color = 'orange'
    elif score < 9:
        color = 'yellow'
    else:
        color = 'brightgreen'

    # Create badge markdown
    badge_md = f"![Pylint Score](https://img.shields.io/badge/Pylint-{score:.2f}-{color}.svg)"
    print(f"Pylint score: {score:.2f}")

    return badge_md

def update_readme(badge_md):
    # Read the current README.md
    with open('README.md', 'r') as file:
        readme_contents = file.read()

    # Update the README.md with the new badge
    updated_contents = re.sub(r'!\[Pylint Score\]\(https://img.shields.io/badge/.*?.svg\)', badge_md, readme_contents)

    with open('README.md', 'w') as file:
        file.write(updated_contents)

    print("README.md updated with new badge")

def check_readme(badge_md):
    # Read the current README.md
    with open('README.md', 'r') as file:
        readme_contents = file.read()

    # Check if the badge needs to be updated
    if badge_md not in readme_contents:
        print("README.md needs to be updated with the new badge")
        exit(1)
    else:
        print("README.md is up-to-date with the new badge")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run pylint and update or check README.md badge.')
    parser.add_argument('--check', action='store_true', help='Check if the README.md badge is up-to-date')
    
    args = parser.parse_args()
    badge_md = run_pylint()

    if args.check:
        check_readme(badge_md)
    else:
        update_readme(badge_md)
