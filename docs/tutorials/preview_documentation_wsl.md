# Preview the Documentation Locally with WSL

This advanced-user tutorial builds the FireBench documentation inside Windows Subsystem for Linux
(WSL) and serves the generated HTML to a browser running on Windows. Use this workflow to review
documentation changes before opening a pull request.

## 1. Open the repository in WSL

Start a WSL terminal and change to the FireBench repository root, the directory containing
`pyproject.toml` and `Makefile`:

```bash
cd /path/to/firebench
```

If you use a virtual environment, activate it before continuing.

## 2. Install the development and documentation tools

Install FireBench in editable mode with both optional dependency groups:

```bash
python -m pip install -e ".[dev,docs]"
```

Installing both groups together provides the test tools and the complete Sphinx toolchain,
including the `sphinx_click` extension.

## 3. Build the HTML documentation

```bash
make docs
```

Sphinx writes the generated site to `docs/_build/html`. Resolve any errors reported by the build
before starting the preview server.

## 4. Start a local web server

From the repository root, run:

```bash
python -m http.server --directory docs/_build/html 8000
```

Keep this terminal open while reviewing the site. The final line should indicate that the server
is listening on port 8000.

## 5. Open the site from Windows

Open a Windows browser and visit `http://localhost:8000`. WSL normally forwards this address to
the server running in the Linux environment.

Navigate through the pages you changed and check links, code blocks, navigation entries, and
layout at more than one browser width.

## 6. Rebuild after making changes

The basic server does not rebuild the site automatically. After editing a documentation source
file, open another WSL terminal in the repository, activate the same environment, and run:

```bash
make docs
```

Refresh the browser after the command finishes. Stop the preview server with `Ctrl+C` when the
review is complete.

## 7. Run the contributor checks

Before submitting documentation changes, reproduce the strict CI build and validate maintained
documentation examples and local links:

```bash
make docs-strict
python -m pytest tests/unit/test_documentation.py
```

Run the external-link check separately because remote sites can be temporarily unavailable:

```bash
make docs-linkcheck
```

If Windows cannot reach `localhost:8000`, confirm that the server is still running and that no
other process is using port 8000. You can select another port, such as 8080, in both the server
command and browser address.
