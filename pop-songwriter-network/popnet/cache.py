"""Tiny cache: if a file exists, load it; if not, run the download and save it."""
import json
import re
from pathlib import Path
from typing import Any, Callable


def safe_name(text: str) -> str:
    """Turn any title into a safe file name, e.g. 'Ke$ha' -> 'Ke_ha'."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")[:150]


def cached_json(path: Path, fetch: Callable[[], Any]) -> Any:
    """Return the data in `path`; if missing, call `fetch()` and save the result."""
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def save_json(path: Path, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
