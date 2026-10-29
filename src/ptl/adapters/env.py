"""Resolve secrets from the environment, falling back to a local .env.

Lookup order for a name: process environment first, then the nearest
`.env` file walking up from `start` (default: working directory). Only
truthy values count; empty assignments are treated as unset. Values are
never logged or printed by this module.
"""
import os


def _parse_dotenv(path):
    found = {}
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return found
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        name, sep, value = line.partition("=")
        if not sep or not name.strip():
            continue
        value = value.strip()
        if (len(value) >= 2 and value[0] == value[-1]
                and value[0] in "\"'"):
            value = value[1:-1]
        if name.strip() and value:
            found[name.strip()] = value
    return found


def resolve_secret(name, default=None, start=None):
    """Return the secret value or `default` when nowhere found."""
    hit = os.environ.get(name)
    if hit:
        return hit
    root = os.path.abspath(start or os.getcwd())
    while True:
        candidate = os.path.join(root, ".env")
        if os.path.isfile(candidate):
            hit = _parse_dotenv(candidate).get(name)
            if hit:
                return hit
        parent = os.path.dirname(root)
        if parent == root:
            return default
        root = parent
