"""Tests for the aegis-user CLI.

The repo had no tests at all, and `add-file` read every secret with
`read_text()` — so any binary file a user pointed it at was corrupted or
raised UnicodeDecodeError. Nothing caught it because nothing ran.
"""

from pathlib import Path

from typer.testing import CliRunner

from aegis_user.cli import app

from .conftest import decrypt, requires

pytestmark = requires("age", "age-keygen")

runner = CliRunner()


def out(result) -> str:
    """Everything the command printed.

    Errors go to stderr, which the runner keeps separate from stdout.
    """
    return result.output


# =============================================================================
# add-file: arbitrary bytes
# =============================================================================

def test_add_file_preserves_binary(user_repo: Path, keypair):
    """A binary secret must survive the round trip byte for byte.

    p12 bundles, DER certificates and keytabs are all things a user will
    reasonably hand to add-file.
    """
    private, _ = keypair
    payload = bytes(range(256)) * 4
    source = user_repo.parent / "cert.p12"
    source.write_bytes(payload)

    result = runner.invoke(app, ["add-file", "cert", str(source)])

    assert result.exit_code == 0, result.stdout
    assert decrypt(user_repo / "files" / "cert.age", private) == payload


def test_add_file_preserves_invalid_utf8(user_repo: Path, keypair):
    """Bytes that are not valid UTF-8 at all used to raise on read."""
    private, _ = keypair
    payload = b"\xff\xfe\x00\x01not utf-8 \x80\x90"
    source = user_repo.parent / "raw.bin"
    source.write_bytes(payload)

    result = runner.invoke(app, ["add-file", "raw", str(source)])

    assert result.exit_code == 0, result.stdout
    assert decrypt(user_repo / "files" / "raw.age", private) == payload


def test_add_file_preserves_text_exactly(user_repo: Path, keypair):
    """Text files keep their trailing newline; add-file is not add-env."""
    private, _ = keypair
    payload = "[default]\naws_access_key_id = AKIA...\n"
    source = user_repo.parent / "credentials"
    source.write_text(payload)

    runner.invoke(app, ["add-file", "aws-creds", str(source)])

    assert decrypt(user_repo / "files" / "aws-creds.age", private) == payload.encode()


def test_add_file_missing_source(user_repo: Path):
    result = runner.invoke(app, ["add-file", "nope", str(user_repo / "absent")])

    assert result.exit_code == 1
    assert "File not found" in out(result)


# =============================================================================
# add-env: text, with a clear failure for non-text
# =============================================================================

def test_add_env_value(user_repo: Path, keypair):
    private, _ = keypair

    result = runner.invoke(app, ["add-env", "GITHUB_TOKEN", "ghp_example"])

    assert result.exit_code == 0, result.stdout
    assert decrypt(user_repo / "env" / "GITHUB_TOKEN.age", private) == b"ghp_example"


def test_add_env_strips_trailing_newline(user_repo: Path, keypair):
    """An env var with a stray newline breaks whatever consumes it."""
    private, _ = keypair
    source = user_repo.parent / "token.txt"
    source.write_text("ghp_example\n")

    runner.invoke(app, ["add-env", "TOKEN", "--file", str(source)])

    assert decrypt(user_repo / "env" / "TOKEN.age", private) == b"ghp_example"


def test_add_env_rejects_binary_file_clearly(user_repo: Path):
    """Non-text is a usage error with a pointer, not a traceback."""
    source = user_repo.parent / "blob.bin"
    source.write_bytes(b"\xff\xfe\x00binary")

    result = runner.invoke(app, ["add-env", "BLOB", "--file", str(source)])

    assert result.exit_code == 1
    assert "not UTF-8" in out(result)
    assert "add-file" in out(result)
    assert not (user_repo / "env" / "BLOB.age").exists()


def test_add_env_from_stdin(user_repo: Path, keypair):
    private, _ = keypair

    result = runner.invoke(app, ["add-env", "PIPED"], input="from-stdin\n")

    assert result.exit_code == 0, result.stdout
    assert decrypt(user_repo / "env" / "PIPED.age", private) == b"from-stdin"


# =============================================================================
# Repo handling
# =============================================================================

def test_list_reports_both_kinds(user_repo: Path):
    source = user_repo.parent / "f.txt"
    source.write_text("x")
    runner.invoke(app, ["add-env", "TOKEN", "value"])
    runner.invoke(app, ["add-file", "creds", str(source)])

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "TOKEN" in result.stdout
    assert "creds" in result.stdout


def test_overwrite_requires_confirmation(user_repo: Path, keypair):
    private, _ = keypair
    runner.invoke(app, ["add-env", "TOKEN", "first"])

    declined = runner.invoke(app, ["add-env", "TOKEN", "second"], input="n\n")
    assert declined.exit_code != 0
    assert decrypt(user_repo / "env" / "TOKEN.age", private) == b"first"

    accepted = runner.invoke(app, ["add-env", "TOKEN", "second"], input="y\n")
    assert accepted.exit_code == 0
    assert decrypt(user_repo / "env" / "TOKEN.age", private) == b"second"


def test_remove(user_repo: Path):
    runner.invoke(app, ["add-env", "TOKEN", "value"])

    result = runner.invoke(app, ["remove", "TOKEN"], input="y\n")

    assert result.exit_code == 0
    assert not (user_repo / "env" / "TOKEN.age").exists()


def test_missing_repo_is_a_clear_error(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AEGIS_USER", str(tmp_path / "does-not-exist"))

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 1
    assert "does not exist" in out(result)


def test_init_creates_structure(tmp_path: Path, keypair, monkeypatch):
    _, public = keypair
    repo = tmp_path / "new-repo"
    repo.mkdir()
    monkeypatch.setenv("AEGIS_USER", str(repo))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    result = runner.invoke(app, ["init", "--key", public])

    assert result.exit_code == 0, result.stdout
    assert (repo / ".key").read_text().strip() == public
    assert (repo / "env").is_dir()
    assert (repo / "files").is_dir()


def test_init_rejects_non_age_key(tmp_path: Path, monkeypatch):
    repo = tmp_path / "new-repo"
    repo.mkdir()
    monkeypatch.setenv("AEGIS_USER", str(repo))

    result = runner.invoke(app, ["init", "--key", "ssh-ed25519 AAAAC3Nza"])

    assert result.exit_code == 1
    assert "age public key" in out(result)


def test_help_documents_the_environment_variables():
    """A path resolved from the environment is invisible unless it is named."""
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    out = (result.stdout or "") + (getattr(result, "stderr", None) or "")
    assert "AEGIS_USER" in out
