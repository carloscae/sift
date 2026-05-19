from pathlib import Path

import click


@click.group()
@click.version_option()
def main() -> None:
    """sift — vault ingest pipeline."""


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
