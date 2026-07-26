"""Application-root path handling that never relies on the process cwd."""

from __future__ import annotations

import os
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
ROOT_ENV_PATH = APP_ROOT / ".env"


def resolve_app_path(
    value: str | os.PathLike[str] | None,
    fallback: str | os.PathLike[str],
    *,
    app_root: Path = APP_ROOT,
) -> Path:
    """Resolve configured paths relative to the application root, not cwd."""

    configured = str(value).strip() if value is not None and str(value).strip() else str(fallback)
    expanded = Path(os.path.expandvars(os.path.expanduser(configured)))
    return expanded.resolve() if expanded.is_absolute() else (app_root / expanded).resolve()


def safe_named_json(directory: Path, name: str) -> Path:
    """Return a JSON profile path while preventing directory traversal."""

    normalized = name[:-5] if name.lower().endswith(".json") else name
    if not normalized or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in normalized):
        raise ValueError(f"Invalid filter profile name: {name!r}")
    candidate = (directory / f"{normalized}.json").resolve()
    if candidate.parent != directory.resolve():
        raise ValueError(f"Filter profile escapes configured directory: {name!r}")
    return candidate
