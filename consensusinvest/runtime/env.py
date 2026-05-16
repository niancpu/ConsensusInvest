"""Local environment loading for runtime configuration."""

from __future__ import annotations

import os
from pathlib import Path


def load_local_env(path: str | Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Load KEY=VALUE pairs from a UTF-8 .env file into os.environ.

    Existing process environment variables win by default so deployment-level
    configuration can override local files.
    """

    env_path = Path(path) if path is not None else _default_env_path()
    if not env_path.exists():
        return {}

    loaded: dict[str, str] = {}
    for line_number, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), 1):
        parsed = _parse_env_line(raw_line, line_number=line_number, path=env_path)
        if parsed is None:
            continue
        key, value = parsed
        if override or not os.environ.get(key, "").strip():
            os.environ[key] = value
            loaded[key] = value
    return loaded


def _default_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def _parse_env_line(
    raw_line: str,
    *,
    line_number: int,
    path: Path,
) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export ") :].strip()
    if "=" not in line:
        raise ValueError(f"invalid .env line {line_number} in {path}: missing '='")

    key, raw_value = line.split("=", 1)
    key = key.strip()
    if not key or not key.replace("_", "").isalnum() or key[0].isdigit():
        raise ValueError(f"invalid .env line {line_number} in {path}: invalid key")

    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    else:
        value = _strip_inline_comment(value).strip()
    return key, value


def _strip_inline_comment(value: str) -> str:
    for index, char in enumerate(value):
        if char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index]
    return value


__all__ = ["load_local_env"]
