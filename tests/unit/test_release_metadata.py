from datetime import date
from pathlib import Path
import runpy

import yaml

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RELEASE_VERSION = "0.10-dev4"
RELEASE_DATE = date(2026, 8, 7)
ZENODO_CONCEPT_DOI = "10.5281/zenodo.15477459"


def test_release_metadata_is_consistent():
    project_metadata = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    citation_metadata = yaml.safe_load((REPOSITORY_ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    docs_metadata = runpy.run_path(str(REPOSITORY_ROOT / "docs" / "conf.py"))

    assert project_metadata["project"]["version"] == RELEASE_VERSION
    assert citation_metadata["version"] == RELEASE_VERSION
    assert citation_metadata["date-released"] == RELEASE_DATE
    assert citation_metadata["doi"] == ZENODO_CONCEPT_DOI
    assert docs_metadata["version"] == RELEASE_VERSION
    assert docs_metadata["release"] == RELEASE_VERSION
