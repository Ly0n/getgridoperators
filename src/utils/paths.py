from __future__ import annotations
from pathlib import Path

def project_root(start: Path | None = None) -> Path:
    """
    Walk upwards until we find a folder that looks like the repo root.
    Markers: 'src' and 'data' folders.
    """
    p = (start or Path(__file__)).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "src").exists() and (parent / "data").exists():
            return parent
    # fallback: two levels up from this file (src/utils/paths.py -> repo root)
    return Path(__file__).resolve().parents[2]
