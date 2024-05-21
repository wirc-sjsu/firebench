import re
import subprocess

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
    badge_url = f"https://img.shields.io/badge/Pylint-{score:.2f}-{color}.svg"
    badge_md = f"![Pylint Score]({badge_url})"

    # Update README.md
    with open('README.md', 'r') as file:
        readme_contents = file.read()

    updated_contents = re.sub(r'!\[Pylint Score\]\(https://img.shields.io/badge/.*?.svg\)', badge_md, readme_contents)

    with open('README.md', 'w') as file:
        file.write(updated_contents)

    print(output)
    print("README.md updated with new badge")

if __name__ == "__main__":
    run_pylint()
