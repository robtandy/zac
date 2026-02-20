"""Tests for tool implementations against a real filesystem in a temp dir."""

import asyncio
import os
from pathlib import Path

import pytest

from agent.tools import (
    BashTool,
    EditTool,
    ReadTool,
    WriteTool,
    ToolRegistry,
    default_tools,
)


@pytest.fixture
def tmp(tmp_path):
    return tmp_path


class TestBashTool:
    @pytest.mark.asyncio
    async def test_simple_command(self):
        tool = BashTool()
        result = await tool.execute({"command": "echo hello"})
        assert result.output.strip() == "hello"
        assert result.is_error is False

    @pytest.mark.asyncio
    async def test_command_with_nonzero_exit(self):
        tool = BashTool()
        result = await tool.execute({"command": "exit 1"})
        assert result.is_error is True
        assert "Exit code: 1" in result.output

    @pytest.mark.asyncio
    async def test_no_command(self):
        tool = BashTool()
        result = await tool.execute({})
        assert result.is_error is True
        assert "No command" in result.output

    @pytest.mark.asyncio
    async def test_timeout(self):
        tool = BashTool()
        # Patch the timeout to something small for testing
        import agent.tools as tools_mod
        original = tools_mod._BASH_TIMEOUT
        tools_mod._BASH_TIMEOUT = 0.1
        try:
            result = await tool.execute({"command": "sleep 10"})
            assert result.is_error is True
            assert "timed out" in result.output
        finally:
            tools_mod._BASH_TIMEOUT = original

    @pytest.mark.asyncio
    async def test_output_truncation(self):
        tool = BashTool()
        import agent.tools as tools_mod
        original = tools_mod._MAX_OUTPUT
        tools_mod._MAX_OUTPUT = 100
        try:
            result = await tool.execute({"command": "python3 -c 'print(\"x\" * 200)'"})
            assert "truncated" in result.output
            assert len(result.output) < 200
        finally:
            tools_mod._MAX_OUTPUT = original

    @pytest.mark.asyncio
    async def test_stderr_captured(self):
        tool = BashTool()
        result = await tool.execute({"command": "echo err >&2"})
        assert "err" in result.output


class TestReadTool:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp):
        f = tmp / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        tool = ReadTool()
        result = await tool.execute({"file_path": str(f)})
        assert result.is_error is False
        assert "1\tline1" in result.output
        assert "2\tline2" in result.output
        assert "3\tline3" in result.output

    @pytest.mark.asyncio
    async def test_read_missing_file(self):
        tool = ReadTool()
        result = await tool.execute({"file_path": "/nonexistent/file.txt"})
        assert result.is_error is True
        assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_read_with_offset_and_limit(self, tmp):
        f = tmp / "test.txt"
        f.write_text("a\nb\nc\nd\ne\n")
        tool = ReadTool()
        result = await tool.execute({"file_path": str(f), "offset": 2, "limit": 2})
        assert result.is_error is False
        assert "2\tb" in result.output
        assert "3\tc" in result.output
        assert "1\ta" not in result.output
        assert "4\td" not in result.output

    @pytest.mark.asyncio
    async def test_read_no_file_path(self):
        tool = ReadTool()
        result = await tool.execute({})
        assert result.is_error is True


class TestWriteTool:
    @pytest.mark.asyncio
    async def test_write_new_file(self, tmp):
        f = tmp / "new.txt"
        tool = WriteTool()
        result = await tool.execute({"file_path": str(f), "content": "hello"})
        assert result.is_error is False
        assert f.read_text() == "hello"

    @pytest.mark.asyncio
    async def test_overwrite_file(self, tmp):
        f = tmp / "existing.txt"
        f.write_text("old")
        tool = WriteTool()
        result = await tool.execute({"file_path": str(f), "content": "new"})
        assert result.is_error is False
        assert f.read_text() == "new"

    @pytest.mark.asyncio
    async def test_creates_parent_dirs(self, tmp):
        f = tmp / "a" / "b" / "c.txt"
        tool = WriteTool()
        result = await tool.execute({"file_path": str(f), "content": "deep"})
        assert result.is_error is False
        assert f.read_text() == "deep"

    @pytest.mark.asyncio
    async def test_no_file_path(self):
        tool = WriteTool()
        result = await tool.execute({"content": "hello"})
        assert result.is_error is True


class TestEditTool:
    @pytest.mark.asyncio
    async def test_successful_edit(self, tmp):
        f = tmp / "test.txt"
        f.write_text("hello world\ngoodbye world\n")
        tool = EditTool()
        result = await tool.execute({
            "file_path": str(f),
            "old_text": "hello world",
            "new_text": "hi world",
        })
        assert result.is_error is False
        assert f.read_text() == "hi world\ngoodbye world\n"

    @pytest.mark.asyncio
    async def test_text_not_found(self, tmp):
        f = tmp / "test.txt"
        f.write_text("hello world\n")
        tool = EditTool()
        result = await tool.execute({
            "file_path": str(f),
            "old_text": "not here",
            "new_text": "replacement",
        })
        assert result.is_error is True
        assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_ambiguous_match(self, tmp):
        f = tmp / "test.txt"
        f.write_text("aaa\naaa\n")
        tool = EditTool()
        result = await tool.execute({
            "file_path": str(f),
            "old_text": "aaa",
            "new_text": "bbb",
        })
        assert result.is_error is True
        assert "2 times" in result.output

    @pytest.mark.asyncio
    async def test_missing_file(self):
        tool = EditTool()
        result = await tool.execute({
            "file_path": "/nonexistent/file.txt",
            "old_text": "a",
            "new_text": "b",
        })
        assert result.is_error is True
        assert "not found" in result.output.lower()


class TestToolRegistry:
    def test_default_tools(self):
        registry = default_tools()
        schemas = registry.schemas()
        names = {s["function"]["name"] for s in schemas}
        assert names == {"bash", "read", "write", "edit"}

    def test_get_tool(self):
        registry = default_tools()
        assert registry.get("bash") is not None
        assert registry.get("nonexistent") is None

    def test_schema_format(self):
        registry = default_tools()
        for schema in registry.schemas():
            assert schema["type"] == "function"
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]
