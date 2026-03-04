"""Gateway utility functions."""

from __future__ import annotations

import subprocess
from pathlib import Path


def find_web_dist() -> str | None:
    """Auto-discover the web UI dist directory relative to the monorepo.
    
    Walks up from the gateway package to find packages/web/dist.
    Returns the path as a string, or None if not found.
    """
    here = Path(__file__).resolve().parent
    for ancestor in (here, *here.parents):
        candidate = ancestor / "packages" / "web" / "dist"
        if candidate.is_dir() and (candidate / "index.html").is_file():
            return str(candidate)
    return None


def find_web_dir() -> Path | None:
    """Find packages/web directory relative to the monorepo.
    
    Walks up from the gateway package to find packages/web.
    Returns the path, or None if not found.
    """
    here = Path(__file__).resolve().parent
    for ancestor in (here, *here.parents):
        candidate = ancestor / "packages" / "web"
        if candidate.is_dir() and (candidate / "package.json").is_file():
            return candidate
    return None


def ensure_web_node_modules() -> None:
    """Run npm install if node_modules is missing in the web directory."""
    web_dir = find_web_dir()
    if web_dir and not (web_dir / "node_modules").is_dir():
        print("Installing web dependencies...")
        result = subprocess.run(
            ["npm", "install"],
            cwd=str(web_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"npm install failed: {result.stderr}")
        print("Web dependencies installed.")
