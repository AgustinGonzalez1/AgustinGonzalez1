"""Small JSON cache helpers used to avoid re-scanning unchanged data on every run."""
import json
import os

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")


def _path(name):
    return os.path.join(CACHE_DIR, name)


def load(name, default=None):
    path = _path(name)
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def save(name, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
