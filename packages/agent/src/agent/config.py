"""Unified configuration management for Zac.

Handles loading and saving configuration from both:
- User config: ~/.zac/config.toml (user-specific settings)
- Project config: <repo>/zac-config.toml (project-specific settings)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib


# =============================================================================
# User Configuration (~/.zac/config.toml)
# =============================================================================

_USER_CONFIG_DIR = Path.home() / ".zac"
_USER_CONFIG_FILE = _USER_CONFIG_DIR / "config.toml"


def get_user_config_path() -> Path:
    """Get the path to the user configuration file."""
    return _USER_CONFIG_FILE


def load_user_config() -> dict[str, Any]:
    """Load user configuration from ~/.zac/config.toml.
    
    Returns an empty dict if the file doesn't exist or can't be parsed.
    """
    if not _USER_CONFIG_FILE.is_file():
        return {}
    
    try:
        with open(_USER_CONFIG_FILE, "rb") as f:
            return tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as e:
        import logging
        logging.getLogger(__name__).debug(
            "Failed to load user config from %s: %s", _USER_CONFIG_FILE, e
        )
        return {}


def save_user_config(config: dict[str, Any]) -> None:
    """Save user configuration to ~/.zac/config.toml.
    
    Creates the ~/.zac directory if it doesn't exist.
    """
    _USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Build TOML content with comments
    lines = ["# Zac user configuration", ""]
    
    if "model" in config:
        lines.append(f'model = "{config["model"]}"')
    if "reasoning_effort" in config:
        lines.append(f'reasoning_effort = "{config["reasoning_effort"]}"')
    
    # Add any other keys generically
    for key, value in config.items():
        if key not in ("model", "reasoning_effort"):
            if isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            else:
                lines.append(f"{key} = {value}")
    
    _USER_CONFIG_FILE.write_text("\n".join(lines) + "\n")


# =============================================================================
# Project Configuration (<repo>/zac-config.toml)
# =============================================================================

def get_project_config_path(repo_root: Path) -> Path:
    """Get the path to the project configuration file."""
    return repo_root / "zac-config.toml"


def load_project_config(repo_root: Path) -> dict[str, Any]:
    """Load project configuration from <repo>/zac-config.toml.
    
    Returns an empty dict if the file doesn't exist or can't be parsed.
    """
    config_file = get_project_config_path(repo_root)
    if not config_file.is_file():
        return {}
    
    try:
        with open(config_file, "rb") as f:
            return tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as e:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to load project config from %s: %s", config_file, e
        )
        return {}


# =============================================================================
# Convenience Functions
# =============================================================================

def get_api_key(repo_root: Path | None = None) -> str | None:
    """Get the OpenRouter API key.
    
    Checks in order:
    1. OPENROUTER_API_KEY environment variable
    2. Project config (open-router-api-key)
    3. User config (open-router-api-key)
    
    Returns None if not found.
    """
    # Check environment variable first
    env_key = os.environ.get("OPENROUTER_API_KEY")
    if env_key:
        return env_key
    
    # Check project config
    if repo_root:
        project_config = load_project_config(repo_root)
        if "open-router-api-key" in project_config:
            return project_config["open-router-api-key"]
    
    # Check user config
    user_config = load_user_config()
    if "open-router-api-key" in user_config:
        return user_config["open-router-api-key"]
    
    return None


def get_model() -> str | None:
    """Get the default model ID from user config."""
    user_config = load_user_config()
    return user_config.get("model")


def get_reasoning_effort() -> str | None:
    """Get the default reasoning effort from user config."""
    user_config = load_user_config()
    return user_config.get("reasoning_effort")


def save_model_preferences(model: str, reasoning_effort: str) -> None:
    """Save model preferences to user config."""
    config = load_user_config()
    config["model"] = model
    config["reasoning_effort"] = reasoning_effort
    save_user_config(config)
