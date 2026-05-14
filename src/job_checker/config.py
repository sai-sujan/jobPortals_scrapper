from pathlib import Path
from typing import Any, Dict

import yaml


ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data


def load_config(root: Path = ROOT) -> Dict[str, Any]:
    return {
        "sites": load_yaml(root / "config" / "sites.yaml"),
        "profile": load_yaml(root / "config" / "profile.yaml"),
    }
