"""Launch the TUI, replacing the current process."""

from __future__ import annotations

import os
import shutil

from .paths import DefaultPaths


def launch(
    *,
    host: str = "0.0.0.0",
    port: int = 8765,
    use_tls: bool = True,
    paths: DefaultPaths | None = None,
) -> None:
    """Replace the current process with the TUI (npx tsx).

    Sets ZAC_GATEWAY_URL and exec's into the TUI process so it gets
    direct terminal control and clean signal handling.
    """
    paths = paths or DefaultPaths()

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
