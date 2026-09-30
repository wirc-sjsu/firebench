import json
import sys

import pytest

from firebench.acquisition import cache


def test_cache_dir_environment_variable_takes_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv(cache.CACHE_DIR_ENV, str(tmp_path / "custom"))

    assert cache.get_cache_dir() == (tmp_path / "custom").resolve()
    assert (tmp_path / "custom").is_dir()
    assert "environment variable" in cache.cache_dir_source()


@pytest.mark.skipif(sys.platform in ("win32", "darwin"), reason="XDG layout is Linux-specific")
def test_cache_dir_defaults_to_xdg_cache_home_without_prompting(monkeypatch, tmp_path):
    monkeypatch.delenv(cache.CACHE_DIR_ENV, raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("cache resolution must not prompt"))

    assert cache.get_cache_dir(create=False) == tmp_path / "firebench"
    assert cache.cache_dir_source() == "platform default"


def test_config_dir_environment_variable_takes_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv(cache.CONFIG_DIR_ENV, str(tmp_path / "cfg"))

    assert cache.config_dir() == tmp_path / "cfg"


def test_cache_subdir_is_created_below_the_root(tmp_path):
    path = cache.cache_subdir("hrrr", "20210820", root=tmp_path)

    assert path == tmp_path / "hrrr" / "20210820"
    assert path.is_dir()


def test_atomic_write_json_leaves_no_temporary_file(tmp_path):
    target = tmp_path / "a" / "meta.json"

    cache.atomic_write_json(target, {"b": 1, "a": [1, 2]})

    assert json.loads(target.read_text()) == {"a": [1, 2], "b": 1}
    assert [path.name for path in target.parent.iterdir()] == ["meta.json"]


def test_directory_usage_counts_nested_files(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "f").write_bytes(b"12345")
    (tmp_path / "g").write_bytes(b"12")

    assert cache.directory_usage(tmp_path) == (2, 7)
    assert cache.directory_usage(tmp_path / "missing") == (0, 0)


@pytest.mark.parametrize(
    ("n_bytes", "expected"),
    ((0, "0 B"), (999, "999 B"), (1500, "1.5 KB"), (2_500_000_000, "2.5 GB"), (3 * 10**15, "3000.0 TB")),
)
def test_format_bytes(n_bytes, expected):
    assert cache.format_bytes(n_bytes) == expected
