from pathlib import Path

from .config import Settings
from .runtime_config import build_runtime_preferences, build_cache_identity, install_runtime_config


def run_conversion(
    job: dict,
    settings: Settings,
    input_path: Path,
    output_path: Path,
    progress_callback,
    cache_path: str | None = None,
    cache_only: bool = False,
) -> str | None:
    runtime_preferences = build_runtime_preferences(
        job,
        settings,
        cache_enabled=cache_path is not None,
        cache_path=cache_path,
    )
    install_runtime_config(runtime_preferences)
    from calibre_plugins.ebook_translator.lib.conversion import convert_item

    convert_item(
        ebook_title=f"Job {job['id']}",
        input_path=str(input_path),
        output_path=str(output_path),
        source_lang=job["source_lang"],
        target_lang=job["target_lang"],
        cache_only=cache_only,
        is_batch=False,
        format=job["input_format"],
        encoding="utf-8",
        direction="auto",
        notification=progress_callback,
    )
    if cache_path is None:
        return None
    cache_id = build_cache_identity(job, settings, str(input_path), encoding="utf-8")
    return str(Path(cache_path) / "cache" / f"{cache_id}.db")
