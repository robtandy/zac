from unittest.mock import patch, MagicMock
from pathlib import Path

from cli.paths import DefaultPaths
from cli.tui import launch


def test_launch_sets_gateway_url_and_execs(tmp_path):
    paths = DefaultPaths(tmp_path)
    with patch("cli.tui.shutil.which", return_value="/usr/bin/npx"), \
         patch("cli.tui.os.execvpe") as mock_exec:
        launch(host="0.0.0.0", port=9000, use_tls=True, paths=paths)

        mock_exec.assert_called_once()
        args = mock_exec.call_args
        assert args[0][0] == "/usr/bin/npx"
        assert args[0][1] == ["npx", "tsx", str(paths.tui_entry)]
        env = args[0][2]
        assert env["ZAC_GATEWAY_URL"] == "wss://localhost:9000"


def test_launch_no_tls_uses_ws_scheme(tmp_path):
    paths = DefaultPaths(tmp_path)
    with patch("cli.tui.shutil.which", return_value="/usr/bin/npx"), \
         patch("cli.tui.os.execvpe") as mock_exec:
        launch(host="0.0.0.0", port=8765, use_tls=False, paths=paths)

        env = mock_exec.call_args[0][2]
        assert env["ZAC_GATEWAY_URL"] == "ws://localhost:8765"


def test_launch_raises_if_npx_not_found(tmp_path):
    paths = DefaultPaths(tmp_path)
    with patch("cli.tui.shutil.which", return_value=None):
        try:
            launch(paths=paths)
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "npx not found" in str(e)
