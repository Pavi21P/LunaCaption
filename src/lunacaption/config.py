"""Dependency-free model settings shared by inference and diagnostics."""

import os
from pathlib import Path

MODEL_ID = "Salesforce/blip-image-captioning-base"
MODEL_REVISION = "82a37760796d32b1411fe092ab5d4e227313294b"
LENGTHS = {"Short": 20, "Standard": 35, "Long": 60}


def default_cache() -> Path:
    # LUMACAPTION_CACHE is the variable name used before the project was renamed.
    override = os.environ.get("LUNACAPTION_CACHE") or os.environ.get("LUMACAPTION_CACHE")
    if override:
        return Path(override).expanduser().resolve()
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache"))
    cache = base / "LunaCaption" / "models"
    legacy = base / "LumaCaption" / "models"
    # Reuse a model downloaded under the previous name instead of fetching ~1 GB again.
    if not cache.exists() and legacy.is_dir():
        return legacy
    return cache
