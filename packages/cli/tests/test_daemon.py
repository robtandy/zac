import os
import signal

from cli.daemon import status, start, stop, _read_pid, _is_alive
from cli.paths import DefaultPaths


def test_status_returns_none_when_no_pid_file(tmp_path):
    paths = DefaultPaths(tmp_path)
    assert status(paths) is None


def test_status_returns_none_for_stale_pid(tmp_path):
    paths = DefaultPaths(tmp_path)
    paths.pid_dir.mkdir(parents=True)
    # Use a PID that almost certainly doesn't exist
    paths.pid_file.write_text("99999999")
    assert status(paths) is None
    assert not paths.pid_file.exists()


def test_status_returns_pid_for_running_process(tmp_path):
    paths = DefaultPaths(tmp_path)
    paths.pid_dir.mkdir(parents=True)
    # Use our own PID (definitely alive)
    paths.pid_file.write_text(str(os.getpid()))
    assert status(paths) == os.getpid()


def test_read_pid_returns_none_for_missing_file(tmp_path):
    assert _read_pid(tmp_path / "nonexistent") is None


def test_read_pid_returns_none_for_bad_content(tmp_path):
    f = tmp_path / "pid"
    f.write_text("not-a-number")
    assert _read_pid(f) is None


def test_is_alive_returns_true_for_self():
    assert _is_alive(os.getpid())


def test_is_alive_returns_false_for_bogus_pid():
    assert not _is_alive(99999999)


def test_stop_when_not_running(tmp_path, capsys):
    paths = DefaultPaths(tmp_path)
    assert stop(paths) is False
    assert "not running" in capsys.readouterr().out
