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


def _resolve_config(vault: str | None):
    if vault is None:
        vault = os.environ.get("SIFT_VAULT", str(Path.cwd()))
    config_path = Path(vault) / "vault-ingest.yaml"
    return load_config(config_path)


@main.command()
@click.argument("vault_path", type=click.Path(file_okay=False, resolve_path=True))
def init(vault_path: str) -> None:
    """Scaffold a vault: raw/, captures/, .vault-ingest/, vault-ingest.yaml."""
    vault = Path(vault_path)
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "raw").mkdir(exist_ok=True)
    (vault / "captures").mkdir(exist_ok=True)
    (vault / ".vault-ingest").mkdir(exist_ok=True)

    config_path = vault / "vault-ingest.yaml"
    if not config_path.exists():
        config_path.write_text(_default_config(vault))

    click.echo(f"✓ Initialised vault at {vault}")


@main.command()
@click.argument("target")
@click.option("--now", is_flag=True, help="Process immediately instead of queueing.")
@_vault_option
def add(target: str, now: bool, vault: str | None) -> None:
    """Queue a URL or file for processing."""
    config = _resolve_config(vault)
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
def run(upgrade_extractors: bool, vault: str | None) -> None:
    """Process all pending items in the queue."""
    if upgrade_extractors:
        import subprocess
        click.echo("Upgrading yt-dlp…")
        subprocess.run(
            ["uv", "pip", "install", "--upgrade", "yt-dlp"],
            check=False,
        )
    config = _resolve_config(vault)
    process_pending(config)
    click.echo("✓ Run complete")


@main.command()
@_vault_option
def status(vault: str | None) -> None:
    """Show queue status."""
    config = _resolve_config(vault)
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
        "    model_stt: groq/whisper-large-v3-turbo\n"
        "    model_text: google/gemini-2.5-flash-lite\n"
        "    model_vision: google/gemini-2.5-flash\n"
    )
