import logging
import stat
import sys

import pytest
from click.testing import CliRunner

from firebench.acquisition import keys
from firebench.cli import main


@pytest.fixture(autouse=True)
def _isolated_config(monkeypatch, tmp_path):
    monkeypatch.setenv("FIREBENCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("SYNOPTIC_TOKEN", raising=False)
    return tmp_path / "config"


def test_missing_key_is_reported_with_every_place_searched():
    resolution = keys.resolve_key("synoptic")

    assert not resolution.found
    assert resolution.value is None
    message = keys.missing_key_message(resolution)
    assert "environment variable SYNOPTIC_TOKEN" in message
    assert str(keys.key_path("synoptic")) in message
    assert "firebench keys set synoptic" in message
    assert "https://customer.synopticdata.com/" in message


def test_stored_key_is_resolved(_isolated_config):
    path = keys.set_key("synoptic", "  abc123  \n")

    resolution = keys.resolve_key("synoptic")
    assert resolution.value == "abc123"
    assert resolution.source == f"stored key {path}"
    assert path.parent == _isolated_config / "credentials"


def test_environment_variable_overrides_the_stored_key(monkeypatch):
    keys.set_key("synoptic", "stored")
    monkeypatch.setenv("SYNOPTIC_TOKEN", "from-env")

    resolution = keys.resolve_key("synoptic")
    assert resolution.value == "from-env"
    assert resolution.source == "environment variable SYNOPTIC_TOKEN"


def test_explicit_key_file_overrides_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SYNOPTIC_TOKEN", "from-env")
    key_file = tmp_path / "token.txt"
    key_file.write_text("# comment\nfrom-file\n")

    assert keys.resolve_key("synoptic", explicit_file=key_file).value == "from-file"


def test_explicit_key_file_that_does_not_exist_is_a_hard_error(monkeypatch, tmp_path):
    monkeypatch.setenv("SYNOPTIC_TOKEN", "from-env")

    with pytest.raises(keys.KeyConfigError, match="does not exist"):
        keys.resolve_key("synoptic", explicit_file=tmp_path / "typo.txt")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_stored_key_is_private_to_the_user():
    path = keys.set_key("synoptic", "secret")

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_key_readable_by_others_triggers_a_warning(caplog):
    path = keys.set_key("synoptic", "secret")
    path.chmod(0o644)

    with caplog.at_level(logging.WARNING):
        keys.resolve_key("synoptic")
    assert "chmod 600" in caplog.text
    assert "secret" not in caplog.text


def test_anonymous_service_needs_no_key():
    resolution = keys.resolve_key("hrrr")

    assert resolution.found
    assert resolution.anonymous


def test_unknown_service_gets_a_generic_environment_variable():
    assert keys.service_info("my-api").env_var == "MY_API_KEY"


@pytest.mark.parametrize("name", ("", "../etc", "Synoptic Token", "a/b"))
def test_invalid_service_names_are_rejected(name):
    with pytest.raises(keys.KeyConfigError):
        keys.service_info(name)


@pytest.mark.parametrize("value", ("", "   ", "two\nlines"))
def test_empty_or_multiline_keys_are_rejected(value):
    with pytest.raises(keys.KeyConfigError):
        keys.set_key("synoptic", value)


def test_remove_key():
    keys.set_key("synoptic", "secret")

    assert keys.remove_key("synoptic") is True
    assert keys.remove_key("synoptic") is False
    assert keys.resolve_key("synoptic").value is None


def test_list_keys_includes_stored_custom_services():
    keys.set_key("my-api", "k")

    names = [resolution.service for resolution in keys.list_keys()]
    assert names[:2] == ["synoptic", "hrrr"]
    assert "my-api" in names


def test_fingerprint_does_not_reveal_the_key():
    value = "abcdefghijklmnop"

    printed = keys.fingerprint(value)
    assert value not in printed
    assert printed.startswith("16 chars, sha256:")


def test_redact_removes_values_and_query_string_tokens():
    text = "GET https://api/x?token=abc123&bbox=1,2 failed with secret-xyz"

    redacted = keys.redact(text, secrets=("secret-xyz",))
    assert "abc123" not in redacted
    assert "secret-xyz" not in redacted
    assert "token=***" in redacted
    assert "bbox=1,2" in redacted


def test_cli_keys_set_from_stdin_list_check_and_remove():
    runner = CliRunner()

    stored = runner.invoke(main, ["keys", "set", "synoptic", "--stdin"], input="my-secret-token\n")
    listed = runner.invoke(main, ["keys", "list"])
    checked = runner.invoke(main, ["keys", "check", "synoptic"])
    removed = runner.invoke(main, ["keys", "remove", "synoptic"])

    for result in (stored, listed, checked, removed):
        assert result.exit_code == 0, result.output
        assert "my-secret-token" not in result.output
    assert "Stored synoptic key" in stored.output
    assert "synoptic  set" in listed.output
    assert "hrrr      not needed" in listed.output
    assert "-> stored key" in checked.output
    assert "Removed stored synoptic key." in removed.output


def test_cli_keys_set_with_hidden_prompt_requires_confirmation():
    runner = CliRunner()

    result = runner.invoke(main, ["keys", "set", "synoptic"], input="tok\ntok\n")

    assert result.exit_code == 0, result.output
    assert keys.resolve_key("synoptic").value == "tok"
    assert "tok\n" not in result.output


def test_cli_keys_set_refuses_anonymous_service():
    result = CliRunner().invoke(main, ["keys", "set", "hrrr", "--stdin"], input="x\n")

    assert result.exit_code != 0
    assert "needs no key" in result.output


def test_cli_keys_check_reports_how_to_add_a_missing_key():
    result = CliRunner().invoke(main, ["keys", "check", "synoptic"])

    assert result.exit_code == 0, result.output
    assert "synoptic: missing" in result.output
    assert "firebench keys set synoptic" in result.output


def test_cli_cache_info_and_clean(monkeypatch, tmp_path):
    monkeypatch.setenv("FIREBENCH_CACHE_DIR", str(tmp_path / "cache"))
    (tmp_path / "cache" / "hrrr").mkdir(parents=True)
    (tmp_path / "cache" / "hrrr" / "f.grib2").write_bytes(b"x" * 10)
    (tmp_path / "cache" / "unrelated").mkdir()
    runner = CliRunner()

    info = runner.invoke(main, ["cache", "info"])
    cleaned = runner.invoke(main, ["cache", "clean", "--yes"])

    assert info.exit_code == 0, info.output
    assert "hrrr" in info.output and "10 B" in info.output
    assert cleaned.exit_code == 0, cleaned.output
    assert not (tmp_path / "cache" / "hrrr").exists()
    assert (tmp_path / "cache" / "unrelated").is_dir()
