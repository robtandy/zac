"""CLI entry point for the `zac` command."""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Annotated, Optional

import typer

from agent.config import get_api_key as _get_api_key_from_config, save_user_config, load_user_config

from . import daemon, tui, fix
from .paths import DefaultPaths

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8765
DEFAULT_LOG_LEVEL = "info"

app = typer.Typer(help="Zac agent CLI", invoke_without_command=True)


def _get_api_key(paths: DefaultPaths) -> str:
    """Get the OpenRouter API key, prompting user if necessary."""
    # Try to get from environment or config
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key:
        return api_key
    
    # Try project config
    project_config_path = paths.config_file
    if project_config_path.is_file():
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        
        try:
            with open(project_config_path, "rb") as f:
                project_config = tomllib.load(f)
                if "open-router-api-key" in project_config:
                    return project_config["open-router-api-key"]
        except Exception:
            pass
    
    # Try user config
    user_config = load_user_config()
    if "open-router-api-key" in user_config:
        return user_config["open-router-api-key"]

    # Prompt user and save to user config
    print("OpenRouter API key not found.")
    print("You can get one from https://openrouter.ai/settings")
    api_key = input("Enter your OpenRouter API key: ").strip()

    if not api_key:
        print("Error: API key is required", file=sys.stderr)
        raise typer.Exit(1)

    # Save to user config instead of project config
    user_config = load_user_config()
    user_config["open-router-api-key"] = api_key
    save_user_config(user_config)
    print(f"Config saved to {Path.home() / '.zac' / 'config.toml'}")
    return api_key


def _run_user_prompt(prompt: str, model: str | None, api_key: str) -> None:
    """Run the agent with a user prompt and print the response to stdout."""
    import asyncio

    from agent.client import AgentClient
    from agent.events import EventType

    async def _async_run():
        client = AgentClient(model=model)
        await client.start()

        try:
            async for event in client.prompt(prompt):
                if event.type == EventType.TEXT_DELTA:
                    print(event.delta, end="", flush=True)
                elif event.type == EventType.ERROR:
                    print(f"\nError: {event.message}", file=sys.stderr)
                    raise typer.Exit(1)
            print()
        finally:
            await client.stop()

    asyncio.run(_async_run())


@app.callback()
def main_callback(
    ctx: typer.Context,
    host: Annotated[str, typer.Option("--host", help="Bind address")] = DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", help="Port")] = DEFAULT_PORT,
    tls_cert: Annotated[str | None, typer.Option("--tls-cert", help="TLS certificate file")] = None,
    tls_key: Annotated[str | None, typer.Option("--tls-key", help="TLS private key file")] = None,
    no_tls: Annotated[bool, typer.Option("--no-tls", help="Disable TLS")] = False,
    system_prompt_file: Annotated[str | None, typer.Option("--system-prompt-file", help="Path to system prompt file")] = None,
    model: Annotated[str | None, typer.Option("--model", help="Model ID")] = None,
    log_file: Annotated[str | None, typer.Option("--log-file", help="Gateway log file path")] = None,
    log_level: Annotated[str, typer.Option("--log-level", help="Log level")] = DEFAULT_LOG_LEVEL,
    conversation_log: Annotated[str | None, typer.Option("--conversation-log", help="Log conversation to file")] = None,
    restart_gateway: Annotated[bool, typer.Option("--restart-gateway", help="Restart gateway before connecting")] = False,
    gateway: Annotated[str | None, typer.Option("--gateway", help="Connect to remote gateway URL")] = None,
    user_prompt: Annotated[str | None, typer.Option("--user-prompt", help="Send prompt and print response (no TUI)")] = None,
) -> None:
    """Start the gateway and launch the TUI (default behavior)."""
    if ctx.invoked_subcommand is not None:
        return

    paths = DefaultPaths()
    api_key = _get_api_key(paths)

    if user_prompt:
        _run_user_prompt(user_prompt, model, api_key)
        return

    if gateway:
        tui.launch(gateway_url=gateway)
        return

    random_port = random.randint(49152, 65535)
    use_tls = not no_tls

    if use_tls:
        cert = tls_cert or str(paths.tls_cert)
        key = tls_key or str(paths.tls_key)
        if not (Path(cert).is_file() and Path(key).is_file()):
            use_tls = False

    opts = {
        "host": host,
        "port": random_port,
        "tls_cert": tls_cert,
        "tls_key": tls_key,
        "no_tls": not use_tls,
        "system_prompt_file": system_prompt_file,
        "model": model,
        "log_file": log_file,
        "log_level": log_level,
        "conversation_log": conversation_log,
        "api_key": api_key,
        "daemon_mode": False,
    }

    pid = None
    try:
        if restart_gateway:
            pid = daemon.restart(**opts)
        else:
            pid = daemon.start(**opts)

        scheme = "wss" if use_tls else "ws"
        gateway_url = f"{scheme}://localhost:{random_port}"
        tui.launch(gateway_url=gateway_url)
    finally:
        if pid is not None:
            daemon.stop(pid=pid)


@app.command()
def actions_server(
    port: Annotated[int, typer.Option("--port", help="Port for the action-system server")] = 8000,
) -> None:
    """Start the action-system server."""
    from action_system.server import run as run_action_server
    import asyncio
    asyncio.run(run_action_server(port=port))


gateway_app = typer.Typer(help="Manage the gateway daemon")
app.add_typer(gateway_app, name="gateway")


@gateway_app.command("start")
def gateway_start(
    host: Annotated[str, typer.Option("--host", help="Bind address")] = DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", help="Port")] = DEFAULT_PORT,
    tls_cert: Annotated[str | None, typer.Option("--tls-cert", help="TLS certificate file")] = None,
    tls_key: Annotated[str | None, typer.Option("--tls-key", help="TLS private key file")] = None,
    no_tls: Annotated[bool, typer.Option("--no-tls", help="Disable TLS")] = False,
    system_prompt_file: Annotated[str | None, typer.Option("--system-prompt-file", help="Path to system prompt file")] = None,
    model: Annotated[str | None, typer.Option("--model", help="Model ID")] = None,
    log_file: Annotated[str | None, typer.Option("--log-file", help="Gateway log file path")] = None,
    log_level: Annotated[str, typer.Option("--log-level", help="Log level")] = DEFAULT_LOG_LEVEL,
    conversation_log: Annotated[str | None, typer.Option("--conversation-log", help="Log conversation to file")] = None,
) -> None:
    """Start the gateway daemon."""
    paths = DefaultPaths()
    api_key = _get_api_key(paths)
    daemon.start(
        host=host,
        port=port,
        tls_cert=tls_cert,
        tls_key=tls_key,
        no_tls=no_tls,
        system_prompt_file=system_prompt_file,
        model=model,
        log_file=log_file,
        log_level=log_level,
        conversation_log=conversation_log,
        api_key=api_key,
    )


@gateway_app.command("stop")
def gateway_stop() -> None:
    """Stop the gateway daemon."""
    daemon.stop()


@gateway_app.command("status")
def gateway_status() -> None:
    """Check gateway status."""
    paths = DefaultPaths()
    pid = daemon.status(paths)
    if pid:
        print(f"Gateway is running (pid {pid})")
    else:
        print("Gateway is not running")
        raise typer.Exit(1)


@gateway_app.command("restart")
def gateway_restart(
    host: Annotated[str, typer.Option("--host", help="Bind address")] = DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", help="Port")] = DEFAULT_PORT,
    tls_cert: Annotated[str | None, typer.Option("--tls-cert", help="TLS certificate file")] = None,
    tls_key: Annotated[str | None, typer.Option("--tls-key", help="TLS private key file")] = None,
    no_tls: Annotated[bool, typer.Option("--no-tls", help="Disable TLS")] = False,
    system_prompt_file: Annotated[str | None, typer.Option("--system-prompt-file", help="Path to system prompt file")] = None,
    model: Annotated[str | None, typer.Option("--model", help="Model ID")] = None,
    log_file: Annotated[str | None, typer.Option("--log-file", help="Gateway log file path")] = None,
    log_level: Annotated[str, typer.Option("--log-level", help="Log level")] = DEFAULT_LOG_LEVEL,
    conversation_log: Annotated[str | None, typer.Option("--conversation-log", help="Log conversation to file")] = None,
) -> None:
    """Restart the gateway daemon."""
    paths = DefaultPaths()
    api_key = _get_api_key(paths)
    daemon.restart(
        host=host,
        port=port,
        tls_cert=tls_cert,
        tls_key=tls_key,
        no_tls=no_tls,
        system_prompt_file=system_prompt_file,
        model=model,
        log_file=log_file,
        log_level=log_level,
        conversation_log=conversation_log,
        api_key=api_key,
    )


# Add fix command directly to main app
from .fix import _run_fix_mode as run_fix
from .fix import DEFAULT_DB_PATH


@app.command("fix")
def fix(
    max_cost: Annotated[float, typer.Option("--max-cost", help="Maximum API cost in dollars")] = 5.0,
    max_issues: Annotated[Optional[int], typer.Option("--max-issues", help="Maximum number of issues to attempt")] = None,
    model: Annotated[Optional[str], typer.Option("--model", help="Model ID")] = None,
    reasoning_effort: Annotated[Optional[str], typer.Option("--reasoning", help="Reasoning effort (low, medium, high, xhigh)")] = None,
    db: Annotated[str, typer.Option("--db", help="Path to issues database")] = DEFAULT_DB_PATH,
    issue: Annotated[Optional[int], typer.Option("--issue", help="Target a specific issue by ID")] = None,
) -> None:
    """Fix GitHub issues automatically."""
    import asyncio
    asyncio.run(run_fix(max_cost, max_issues, model, reasoning_effort, db, issue))


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
