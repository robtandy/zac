"""Tests for the ReadTool and EditTool (pi-mono style)."""
import tempfile
from pathlib import Path

import pytest

from agent.tools import EditTool, ReadTool, ToolResult


@pytest.fixture
def temp_file():
    """Fixture to provide a temp file with test content."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("""# Test file
def hello():
    print("Hello, world!")
    return True
""")
        return f.name


@pytest.mark.asyncio
async def test_read_tool_basic(temp_file):
    """Test that ReadTool can read a file."""
    read_tool = ReadTool()
    result = await read_tool.execute({"path": temp_file})
    
    assert not result.is_error
    assert "def hello" in result.output
    assert "print" in result.output


@pytest.mark.asyncio
async def test_read_tool_with_offset(temp_file):
    """Test that ReadTool supports offset parameter."""
    read_tool = ReadTool()
    result = await read_tool.execute({"path": temp_file, "offset": 2})
    
    assert not result.is_error
    # Should show lines 2 onwards
    assert "print" in result.output


@pytest.mark.asyncio
async def test_read_tool_with_limit(temp_file):
    """Test that ReadTool supports limit parameter."""
    read_tool = ReadTool()
    result = await read_tool.execute({"path": temp_file, "limit": 2})
    
    assert not result.is_error
    # Should show 2 lines plus a note about remaining lines
    assert "def hello():" in result.output
    assert "more lines in file" in result.output


@pytest.mark.asyncio
async def test_read_tool_file_not_found():
    """Test that ReadTool handles file not found errors."""
    read_tool = ReadTool()
    result = await read_tool.execute({"path": "/nonexistent/file.txt"})
    
    assert result.is_error
    assert "File not found" in result.output


@pytest.mark.asyncio
async def test_edit_tool_basic(temp_file):
    """Test that EditTool can replace text."""
    edit_tool = EditTool()
    
    # Edit using oldText/newText pattern (pi-mono style)
    result = await edit_tool.execute({
        "path": temp_file,
        "oldText": 'print("Hello, world!")',
        "newText": 'print("Hello, test!")',
    })
    
    assert not result.is_error, f"Edit failed: {result.output}"
    assert result.diff is not None  # Should return diff
    
    # Verify the edit
    read_tool = ReadTool()
    result = await read_tool.execute({"path": temp_file})
    assert "Hello, test!" in result.output


@pytest.mark.asyncio
async def test_edit_tool_fuzzy_match(temp_file):
    """Test that EditTool fuzzy matches minor whitespace differences."""
    edit_tool = EditTool()
    
    # Old text has trailing space - should still match
    result = await edit_tool.execute({
        "path": temp_file,
        "oldText": 'print("Hello, world!")   ',  # Extra trailing whitespace
        "newText": 'print("Fuzzy match!")',
    })
    
    assert not result.is_error, f"Edit failed: {result.output}"
    
    # Verify the edit
    read_tool = ReadTool()
    result = await read_tool.execute({"path": temp_file})
    assert "Fuzzy match!" in result.output


@pytest.mark.asyncio
async def test_edit_tool_not_found(temp_file):
    """Test that EditTool fails if text not found."""
    edit_tool = EditTool()
    
    result = await edit_tool.execute({
        "path": temp_file,
        "oldText": "this does not exist",
        "newText": "replacement",
    })
    
    assert result.is_error
    assert "Could not find" in result.output


@pytest.mark.asyncio
async def test_edit_tool_returns_diff(temp_file):
    """Test that EditTool returns diff in result."""
    edit_tool = EditTool()
    
    result = await edit_tool.execute({
        "path": temp_file,
        "oldText": 'print("Hello, world!")',
        "newText": 'print("Diff test!")',
    })
    
    assert not result.is_error
    assert result.diff is not None
    assert "+" in result.diff  # Diff should have additions
    assert "-" in result.diff  # Diff should have deletions
