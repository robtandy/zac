"""Launch the TUI, replacing the current process."""

from __future__ import annotations

import os
import shutil
import subprocess

from .paths import DefaultPaths


def _ensure_node_modules(paths: DefaultPaths) -> None:
    """Run npm install if node_modules is missing."""
    tui_dir = paths.tui_entry.parent.parent
    if not (tui_dir / "node_modules").is_dir():
        print("Installing TUI dependencies...")
        result = subprocess.run(
            ["npm", "install"],
            cwd=str(tui_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"npm install failed: {result.stderr}")
        print("TUI dependencies installed.")


def launch(
    *,
    host: str = "0.0.0.0",
    port: int = 8765,
    use_tls: bool = True,
    gateway_url: str | None = None,
    paths: DefaultPaths | None = None,
) -> None:
    """Replace the current process with the TUI (npx tsx).

    Sets ZAC_GATEWAY_URL and exec's into the TUI process so it gets
    direct terminal control and clean signal handling.
    """
    paths = paths or DefaultPaths()

    # Ensure node_modules is installed before launching
    _ensure_node_modules(paths)

    if gateway_url is None:
        scheme = "wss" if use_tls else "ws"
        # TUI connects to localhost regardless of what host the gateway binds
        gateway_url = f"{scheme}://localhost:{port}"

    env = os.environ.copy()
    env["ZAC_GATEWAY_URL"] = gateway_url

    entry = str(paths.tui_entry)

    npx = shutil.which("npx")
    if npx is None:
        raise RuntimeError("npx not found in PATH. Install Node.js to use the TUI.")

    os.execvpe(npx, ["npx", "tsx", entry], env)
