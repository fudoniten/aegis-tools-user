"""Aegis User CLI - Self-service secrets management for users."""

import os
import subprocess
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="aegis-user",
    help="Aegis User Tools - Manage your personal secrets.",
    # \b marks the block as pre-formatted; without it the table is rewrapped
    # into a paragraph and stops being a table.
    epilog="""Environment:
\b
  AEGIS_USER    path to your aegis-secrets-<username> repo. Without it,
                aegis-user uses the current directory, which must already
                look like a user repo (it has a .key, env/ or files/).

Your public key is read from <repo>/.key, falling back to
~/.config/aegis-user/public-key; 'aegis-user init --key=age1...' writes it.""",
    no_args_is_help=True,
)

CONFIG_DIR = Path.home() / ".config" / "aegis-user"
KEY_FILE = CONFIG_DIR / "public-key"


def _is_user_repo(path: Path) -> bool:
    """Check if a path looks like a user secrets repo."""
    return (
        (path / ".key").exists() or 
        (path / "env").exists() or 
        (path / "files").exists()
    )


def get_repo_path(allow_missing: bool = False) -> Path:
    """Get the user's secrets repo path.
    
    Resolution order:
    1. AEGIS_USER environment variable
    2. Current directory (if it looks like a user repo)
    
    Args:
        allow_missing: If True, return cwd even if not a valid repo (for init)
    """
    # Check AEGIS_USER environment variable first
    env_path = os.environ.get("AEGIS_USER")
    if env_path:
        path = Path(env_path)
        if path.exists():
            if _is_user_repo(path) or allow_missing:
                return path
            typer.echo(f"Error: AEGIS_USER points to invalid repo: {env_path}", err=True)
            typer.echo("Directory exists but doesn't look like a user secrets repo.", err=True)
            raise typer.Exit(1)
        typer.echo(f"Error: AEGIS_USER path does not exist: {env_path}", err=True)
        raise typer.Exit(1)
    
    # Check current directory
    cwd = Path.cwd()
    if _is_user_repo(cwd) or allow_missing:
        return cwd
    
    typer.echo("Error: Could not find user secrets repo", err=True)
    typer.echo("", err=True)
    typer.echo("Options:", err=True)
    typer.echo("  1. Run from within your aegis-secrets-<username> repo", err=True)
    typer.echo("  2. Set AEGIS_USER environment variable", err=True)
    raise typer.Exit(1)


def get_public_key() -> str:
    """Get the user's public key for encryption."""
    repo = get_repo_path()
    
    # First check repo's .key file
    repo_key = repo / ".key"
    if repo_key.exists():
        return repo_key.read_text().strip()
    
    # Then check config
    if KEY_FILE.exists():
        return KEY_FILE.read_text().strip()
    
    typer.echo("Error: No public key configured", err=True)
    typer.echo("Run 'aegis-user init --key=<public-key>' first", err=True)
    raise typer.Exit(1)


def encrypt_for_repo(content: str | bytes, output_path: Path) -> None:
    """Encrypt content with the repo's public key.

    Binary clean: bytes are written through unchanged, str is encoded as UTF-8
    first. add-file has to carry whatever the user points it at -- a p12, a
    DER certificate, a keytab -- and reading those as text corrupts or fails.
    """
    public_key = get_public_key()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = content.encode("utf-8") if isinstance(content, str) else content

    cmd = [
        "age", "--encrypt", "--armor",
        "--recipient", public_key,
        "--output", str(output_path),
    ]

    subprocess.run(cmd, input=payload, check=True)


# =============================================================================
# Commands
# =============================================================================

@app.command()
def init(
    key: Optional[str] = typer.Option(None, "--key", "-k", help="Public key from admin"),
    key_file: Optional[Path] = typer.Option(None, "--key-file", "-f", help="File containing public key"),
):
    """Initialize your secrets repo with the public key from admin.
    
    The admin will give you a public key when they run 'aegis add-user'.
    Use that key here to set up your repo.
    """
    if key is None and key_file is None:
        typer.echo("Error: Provide either --key or --key-file", err=True)
        raise typer.Exit(1)
    
    if key_file:
        if not key_file.exists():
            typer.echo(f"Error: Key file not found: {key_file}", err=True)
            raise typer.Exit(1)
        key = key_file.read_text().strip()
    
    # At this point key must be set
    assert key is not None
    
    # Validate it looks like an age public key
    if not key.startswith("age1"):
        typer.echo("Error: Key doesn't look like an age public key (should start with 'age1')", err=True)
        raise typer.Exit(1)
    
    # Try to find/create repo (allow_missing for init)
    repo = get_repo_path(allow_missing=True)
    
    # Save key to repo
    key_path = repo / ".key"
    key_path.write_text(key + "\n")
    
    # Also save to config dir for convenience
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(key + "\n")
    
    # Create directory structure
    (repo / "env").mkdir(exist_ok=True)
    (repo / "files").mkdir(exist_ok=True)
    
    typer.secho("Initialized!", fg=typer.colors.GREEN)
    typer.echo(f"  Repo: {repo}")
    typer.echo(f"  Key saved to: {key_path}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo("  aegis-user add-env GITHUB_TOKEN 'ghp_...'")
    typer.echo("  aegis-user add-file aws-creds ~/.aws/credentials")


@app.command("add-env")
def add_env(
    name: str = typer.Argument(..., help="Environment variable name"),
    value: Optional[str] = typer.Argument(None, help="Value (omit to read from stdin)"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Read value from file"),
):
    """Add an encrypted environment variable.
    
    Examples:
        aegis-user add-env GITHUB_TOKEN ghp_xxxx
        aegis-user add-env API_KEY --file ./key.txt
        echo "secret" | aegis-user add-env MY_SECRET
    """
    repo = get_repo_path()
    
    # Get the value
    if file:
        if not file.exists():
            typer.echo(f"Error: File not found: {file}", err=True)
            raise typer.Exit(1)
        try:
            value = file.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            typer.echo(
                f"Error: {file} is not UTF-8 text.\n"
                f"Environment variables must be text; use 'add-file' for "
                f"binary secrets.",
                err=True,
            )
            raise typer.Exit(1)
    elif value is None:
        # Read from stdin
        import sys
        if sys.stdin.isatty():
            value = typer.prompt("Enter value", hide_input=True)
        else:
            value = sys.stdin.read()
    
    # At this point value must be set
    assert value is not None
    
    # Remove trailing newline if present
    value = value.rstrip("\n")
    
    output_path = repo / "env" / f"{name}.age"
    
    if output_path.exists():
        if not typer.confirm(f"{name} already exists. Overwrite?"):
            raise typer.Abort()
    
    encrypt_for_repo(value, output_path)
    
    typer.secho(f"Added: {name}", fg=typer.colors.GREEN)
    typer.echo(f"  File: {output_path}")
    typer.echo("")
    typer.echo("Don't forget to commit and push!")


@app.command("add-file")
def add_file(
    name: str = typer.Argument(..., help="Name for this secret file"),
    file: Path = typer.Argument(..., help="Path to file to encrypt"),
):
    """Add an encrypted file.
    
    Examples:
        aegis-user add-file aws-creds ~/.aws/credentials
        aegis-user add-file ssh-key ~/.ssh/id_ed25519
    """
    repo = get_repo_path()
    
    if not file.exists():
        typer.echo(f"Error: File not found: {file}", err=True)
        raise typer.Exit(1)
    
    # Bytes, not text: this command takes arbitrary files.
    content = file.read_bytes()
    output_path = repo / "files" / f"{name}.age"
    
    if output_path.exists():
        if not typer.confirm(f"{name} already exists. Overwrite?"):
            raise typer.Abort()
    
    encrypt_for_repo(content, output_path)
    
    typer.secho(f"Added: {name}", fg=typer.colors.GREEN)
    typer.echo(f"  File: {output_path}")
    typer.echo("")
    typer.echo("Don't forget to commit and push!")


@app.command()
def remove(
    name: str = typer.Argument(..., help="Secret name to remove"),
):
    """Remove a secret."""
    repo = get_repo_path()
    
    # Check both env and files
    env_path = repo / "env" / f"{name}.age"
    files_path = repo / "files" / f"{name}.age"
    
    removed = False
    
    if env_path.exists():
        if typer.confirm(f"Remove env var {name}?"):
            env_path.unlink()
            typer.echo(f"Removed: {env_path}")
            removed = True
    
    if files_path.exists():
        if typer.confirm(f"Remove file {name}?"):
            files_path.unlink()
            typer.echo(f"Removed: {files_path}")
            removed = True
    
    if not removed:
        typer.echo(f"Secret not found: {name}")
        raise typer.Exit(1)
    
    typer.echo("")
    typer.echo("Don't forget to commit and push!")


@app.command()
def list():
    """List all secrets in the repo."""
    repo = get_repo_path()
    
    typer.echo(f"Secrets in {repo}:\n")
    
    # List env vars
    env_dir = repo / "env"
    if env_dir.exists():
        env_files = sorted(env_dir.glob("*.age"))
        if env_files:
            typer.echo("Environment variables:")
            for f in env_files:
                size = f.stat().st_size
                typer.echo(f"  {f.stem} ({size} bytes)")
        else:
            typer.echo("Environment variables: (none)")
    
    typer.echo("")
    
    # List files
    files_dir = repo / "files"
    if files_dir.exists():
        file_files = sorted(files_dir.glob("*.age"))
        if file_files:
            typer.echo("Files:")
            for f in file_files:
                size = f.stat().st_size
                typer.echo(f"  {f.stem} ({size} bytes)")
        else:
            typer.echo("Files: (none)")


@app.command()
def status():
    """Show status of the secrets repo."""
    repo = get_repo_path()
    
    typer.echo(f"Repo: {repo}")
    
    # Check key
    key_file = repo / ".key"
    if key_file.exists():
        key = key_file.read_text().strip()
        typer.echo(f"Key: {key[:20]}...")
    else:
        typer.echo("Key: NOT CONFIGURED")
        typer.echo("  Run 'aegis-user init --key=<key>' first")
        return
    
    # Count secrets
    env_count = len(list((repo / "env").glob("*.age"))) if (repo / "env").exists() else 0
    files_count = len(list((repo / "files").glob("*.age"))) if (repo / "files").exists() else 0
    
    typer.echo(f"Env vars: {env_count}")
    typer.echo(f"Files: {files_count}")
    
    # Git status
    import subprocess
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            changes = len([l for l in result.stdout.strip().split("\n") if l])
            if changes:
                typer.echo(f"\nUncommitted changes: {changes}")
            else:
                typer.echo("\nGit: clean")
    except:
        pass


def main():
    app()


if __name__ == "__main__":
    main()
