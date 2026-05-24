import os
import shutil
from pathlib import Path

import click

from sift.config import load_config
from sift.pipeline import process_pending
from sift.queue import Queue


@click.group()
@click.version_option()
def main() -> None:
    """sift — vault ingest pipeline."""


def _vault_option(f):
    return click.option(
        "--vault",
        type=click.Path(file_okay=False, resolve_path=True),
        default=None,
        help="Vault root (defaults to $SIFT_VAULT or current directory).",
    )(f)


def _config_option(f):
    return click.option(
        "--config",
        "config_path",
        type=click.Path(dir_okay=False, resolve_path=True),
        default=None,
        help=(
            "Path to vault-ingest.yaml (overrides $SIFT_CONFIG and the default "
            "<vault>/vault-ingest.yaml)."
        ),
    )(f)


def _resolve_config(vault: str | None, config_path: str | None = None):
    """Resolve the config file path and load it.

    Precedence:
    1. --config CLI flag
    2. $SIFT_CONFIG env var
    3. <vault>/vault-ingest.yaml (where vault = --vault or $SIFT_VAULT or cwd)
    """
    if config_path is None:
        config_path = os.environ.get("SIFT_CONFIG")
    if config_path is None:
        if vault is None:
            vault = os.environ.get("SIFT_VAULT", str(Path.cwd()))
        config_path = str(Path(vault) / "vault-ingest.yaml")
    return load_config(Path(config_path))


@main.command()
@click.argument("vault_path", type=click.Path(file_okay=False, resolve_path=True))
@_config_option
def init(vault_path: str, config_path: str | None) -> None:
    """Scaffold a vault: raw/, captures/, .vault-ingest/, and a config file.

    By default the config is written to <vault>/vault-ingest.yaml.
    Pass --config <path> to write it elsewhere (e.g. a hidden sub-folder
    so the vault root stays clean).
    """
    vault = Path(vault_path)
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "raw").mkdir(exist_ok=True)
    (vault / "captures").mkdir(exist_ok=True)
    (vault / ".vault-ingest").mkdir(exist_ok=True)

    if config_path is None:
        config_file = vault / "vault-ingest.yaml"
    else:
        config_file = Path(config_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)

    if not config_file.exists():
        config_file.write_text(_default_config(vault))

    click.echo(f"✓ Initialised vault at {vault}")
    click.echo(f"  config: {config_file}")


@main.command()
@click.argument("target")
@click.option("--now", is_flag=True, help="Process immediately instead of queueing.")
@_vault_option
@_config_option
def add(target: str, now: bool, vault: str | None, config_path: str | None) -> None:
    """Queue a URL or file for processing."""
    config = _resolve_config(vault, config_path)
    queue = Queue(config)

    if target.startswith(("http://", "https://")):
        queue.enqueue_url(target)
        click.echo(f"✓ Queued URL: {target}")
    else:
        path = Path(target).resolve()
        if not path.exists():
            raise click.ClickException(f"File not found: {path}")
        dest = config.raw_path / path.name
        shutil.copy2(path, dest)
        queue.enqueue_file(dest)
        click.echo(f"✓ Queued file: {dest}")

    if now:
        process_pending(config)
        click.echo("✓ Queue processed")


@main.command()
@click.option("--upgrade-extractors", is_flag=True, help="Upgrade yt-dlp before running.")
@_vault_option
@_config_option
def run(upgrade_extractors: bool, vault: str | None, config_path: str | None) -> None:
    """Process all pending items in the queue."""
    if upgrade_extractors:
        import subprocess
        import sys
        click.echo("Upgrading yt-dlp…")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            click.echo(f"⚠ yt-dlp upgrade failed: {result.stderr.strip()}", err=True)
    config = _resolve_config(vault, config_path)
    process_pending(config)
    click.echo("✓ Run complete")


@main.command()
@_vault_option
@_config_option
def status(vault: str | None, config_path: str | None) -> None:
    """Show queue status."""
    config = _resolve_config(vault, config_path)
    queue = Queue(config)
    pending = queue.pending_items()
    click.echo(f"{len(pending)} pending")
    for entry in pending:
        click.echo(f"  • [{entry.kind}] {entry.source}")


def _default_config(vault: Path) -> str:
    return (
        f"vault: {vault}\n"
        "raw_dir: raw\n"
        "output_dir: captures\n"
        "state_dir: .vault-ingest\n"
        "raw_ttl_days: 7\n"
        "\n"
        "enricher:\n"
        "  backend: openrouter\n"
        "  openrouter:\n"
        "    api_key_env: OPENROUTER_API_KEY\n"
        "    whisper_svc_url: http://localhost:8742\n"
        "    model_text: google/gemini-2.5-flash-lite\n"
        "    model_vision: google/gemini-2.5-flash\n"
    )
