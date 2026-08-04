"""Shared fixtures for the user CLI tests."""

import shutil
import subprocess
from pathlib import Path

import pytest


def requires(*binaries: str):
    """Skip a test when an external tool is unavailable."""
    missing = [b for b in binaries if shutil.which(b) is None]
    return pytest.mark.skipif(bool(missing), reason=f"requires {', '.join(missing)}")


@pytest.fixture
def keypair() -> tuple[str, str]:
    """An age keypair, as (private_key, public_key)."""
    private = subprocess.run(
        ["age-keygen"], capture_output=True, text=True, check=True
    ).stdout.strip()
    public = subprocess.run(
        ["age-keygen", "-y"], input=private,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return private, public


@pytest.fixture
def user_repo(tmp_path: Path, keypair, monkeypatch) -> Path:
    """An initialised user secrets repo, with AEGIS_USER pointing at it."""
    _, public = keypair
    repo = tmp_path / "aegis-secrets-tester"
    (repo / "env").mkdir(parents=True)
    (repo / "files").mkdir(parents=True)
    (repo / ".key").write_text(public + "\n")

    monkeypatch.setenv("AEGIS_USER", str(repo))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return repo


def decrypt(path: Path, private_key: str) -> bytes:
    """Decrypt a secret the way the admin tooling would, as raw bytes."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".key", delete=False) as f:
        f.write(private_key)
        identity = Path(f.name)
    try:
        return subprocess.run(
            ["age", "--decrypt", "--identity", str(identity), str(path)],
            capture_output=True, check=True,
        ).stdout
    finally:
        identity.unlink()
