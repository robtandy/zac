import os
from pathlib import Path

from cli.paths import DefaultPaths, find_repo_root


def test_find_repo_root_finds_zac_mono():
    root = find_repo_root()
    assert (root / "pyproject.toml").is_file()
    assert 'name = "zac-mono"' in (root / "pyproject.toml").read_text()


def test_find_repo_root_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAC_ROOT", str(tmp_path))
    assert find_repo_root() == tmp_path


def test_default_paths():
    root = Path("/fake/root")
    paths = DefaultPaths(root)
    assert paths.root == root
    assert paths.tls_cert == root / "certs" / "tailscale.crt"
    assert paths.tls_key == root / "certs" / "tailscale.key"
    assert paths.system_prompt == root / "packages" / "agent" / "system_prompt"
    assert paths.log_file == root / "gateway.log"
    assert paths.tui_entry == root / "packages" / "tui" / "src" / "index.ts"
    assert paths.pid_file == root / ".zac" / "gateway.pid"
