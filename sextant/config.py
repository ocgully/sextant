"""Per-project configuration — .sextant/config.yaml or config.json.

Sextant avoids a YAML dep: we parse JSON, and if the file is .yaml we
accept a tiny subset (flat key: value; #-comments). Falls back to
reasonable defaults if the file doesn't exist.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_CONFIG: Dict[str, Any] = {
    "risk": "basic",                # off | basic | full
    "format": "text",               # text | json
    "confidence_threshold": 0.7,    # ops below this shown dimly
    "enabled_patterns": "all",      # or comma-separated kinds
    "languages": ["python", "typescript", "javascript", "rust", "go", "markdown"],
}


def _config_path(cwd: Path) -> Path:
    base = cwd / ".sextant"
    # Prefer YAML if present; else JSON.
    for name in ("config.yaml", "config.yml", "config.json"):
        p = base / name
        if p.exists():
            return p
    return base / "config.yaml"  # default path for writes


def _parse_kv_yaml(text: str) -> Dict[str, Any]:
    """Tiny flat-YAML: `key: value` per line; `#` comments; no nesting."""
    out: Dict[str, Any] = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+)$", line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        # strip quotes
        if raw.startswith(("'", '"')) and raw.endswith(raw[0]):
            raw = raw[1:-1]
        # lists: [a, b, c]
        if raw.startswith("[") and raw.endswith("]"):
            items = [x.strip().strip("'\"") for x in raw[1:-1].split(",") if x.strip()]
            out[key] = items
            continue
        # booleans / numbers
        if raw.lower() in ("true", "false"):
            out[key] = raw.lower() == "true"
            continue
        try:
            if "." in raw:
                out[key] = float(raw)
            else:
                out[key] = int(raw)
            continue
        except ValueError:
            pass
        out[key] = raw
    return out


def load(cwd: Optional[Path] = None) -> Dict[str, Any]:
    cwd = cwd or Path.cwd()
    path = _config_path(cwd)
    cfg = dict(DEFAULT_CONFIG)
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix == ".json":
                cfg.update(json.loads(text))
            else:
                cfg.update(_parse_kv_yaml(text))
        except Exception:
            pass
    return cfg


def save(cfg: Dict[str, Any], cwd: Optional[Path] = None) -> Path:
    cwd = cwd or Path.cwd()
    path = _config_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    # prefer JSON for round-trip determinism
    if path.suffix == ".yaml" or path.suffix == ".yml":
        path = path.with_suffix(".json")
    path.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def set_key(key: str, value: str, cwd: Optional[Path] = None) -> Path:
    cfg = load(cwd)
    # coerce common types
    if value.lower() in ("true", "false"):
        cfg[key] = value.lower() == "true"
    else:
        try:
            cfg[key] = int(value)
        except ValueError:
            try:
                cfg[key] = float(value)
            except ValueError:
                cfg[key] = value
    return save(cfg, cwd)


def get_key(key: str, cwd: Optional[Path] = None) -> Any:
    return load(cwd).get(key)
