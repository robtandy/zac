# Text-based read/edit tools (Claude Code style)
#
# This implementation follows Claude Code's approach using old_string/new_string
# for find-and-replace operations instead of hash-based line references.

import asyncio
import json
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    output: str
    is_error: bool = False


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Tool(ABC):
    @abstractmethod
    def definition(self) -> ToolDefinition: ...

    @abstractmethod
    async def execute(self, args: dict[str, Any]) -> ToolResult: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        defn = tool.definition()
        self._tools[defn.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        return [t.definition().to_openai_schema() for t in self._tools.values()]


_MAX_OUTPUT = 30_000
_BASH_TIMEOUT = 120


class BashTool(Tool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="bash",
            description="Execute a bash command and return stdout+stderr.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute.",
                    },
                },
                "required": ["command"],
            },
        )

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        command = args.get("command", "")
        if not command:
            return ToolResult(output="No command provided.", is_error=True)
        try:
            proc = await asyncio.create_subprocess_exec(
                "bash",
                "-c",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=_BASH_TIMEOUT
            )
            output = stdout.decode(errors="replace")
            if len(output) > _MAX_OUTPUT:
                output = output[:_MAX_OUTPUT] + "\n... (output truncated)"
            if proc.returncode != 0:
                output = f"Exit code: {proc.returncode}\n{output}"
            return ToolResult(output=output, is_error=proc.returncode != 0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(
                output=f"Command timed out after {_BASH_TIMEOUT}s.",
                is_error=True,
            )
        except OSError as e:
            return ToolResult(output=f"Failed to execute command: {e}", is_error=True)


class ReadTool(Tool):
    """Read a file and return its contents.
    
    Returns plain file content (no hash prefix) to match Claude Code behavior.
    The edit tool uses old_string/new_string for replacements.
    """

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read",
            description="""
Read a file and return its contents.

Parameters:
- file_path: Absolute path to the file to read.
- offset: Optional line number to start reading from (1-based).
- limit: Optional maximum number of lines to read.

Example usage:
  {"file_path": "/path/to/file.py"}
  {"file_path": "/path/to/file.py", "offset": 10, "limit": 50}
""",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file to read.",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Optional line number to start reading from (1-based).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Optional maximum number of lines to read.",
                    },
                },
                "required": ["file_path"],
            },
        )

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        file_path = args.get("file_path", "")
        offset = args.get("offset", 1)  # 1-based offset
        limit = args.get("limit")

        if not file_path:
            return ToolResult(output="No file_path provided.", is_error=True)
        try:
            path = Path(file_path)
            text = path.read_text()
        except FileNotFoundError:
            return ToolResult(output=f"File not found: {file_path}", is_error=True)
        except OSError as e:
            return ToolResult(output=f"Error reading file: {e}", is_error=True)

        lines = text.splitlines(keepends=True)

        # Apply offset (1-based) and limit
        start_idx = max(0, offset - 1)  # Convert to 0-based
        end_idx = len(lines) if limit is None else start_idx + limit
        
        selected_lines = lines[start_idx:end_idx]
        
        # Add line numbers for reference (similar to Claude Code)
        numbered = []
        for i, line in enumerate(selected_lines, start=start_idx + 1):
            numbered.append(f"{i:4d}| {line.rstrip()}")
        
        output = "\n".join(numbered)
        
        # Add context about total lines if truncated
        if end_idx < len(lines):
            output += f"\n... ({len(lines) - end_idx} more lines)"
        
        return ToolResult(output=output)


class WriteTool(Tool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write",
            description="""
Write content to a file. Creates parent directories if needed.

This will completely overwrite the existing file.

Parameters:
- file_path: Absolute path to the file to write.
- content: Content to write to the file.

Example usage:
  {
    "file_path": "/path/to/file.py",
    "content": "print('Hello, world!')"
  }
""",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file to write.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file.",
                    },
                },
                "required": ["file_path", "content"],
            },
        )

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        file_path = args.get("file_path", "")
        content = args.get("content", "")

        if not file_path:
            return ToolResult(output="No file_path provided.", is_error=True)
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            return ToolResult(output=f"Wrote {len(content)} bytes to {file_path}")
        except OSError as e:
            return ToolResult(output=f"Error writing file: {e}", is_error=True)


class EditTool(Tool):
    """Find and replace text in a file (Claude Code style).
    
    Uses old_string/new_string for text-based find-and-replace,
    similar to Claude Code's Edit tool.
    """

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="edit",
            description="""
Find and replace text in a file using string matching.

This tool finds the old_string text and replaces it with new_string.
The replacement is based on exact text matching - use the exact text
from the file you want to replace.

Parameters:
- file_path: Absolute path to the file to edit.
- old_string: The exact text to find and replace (must match exactly).
- new_string: The replacement text.

Example usage:
  {
    "file_path": "/path/to/file.py",
    "old_string": "def old_function():",
    "new_string": "def new_function():"
  }

For multi-line replacements, include the exact newlines:
  {
    "file_path": "/path/to/file.py",
    "old_string": "def old_func():\n    pass",
    "new_string": "def new_func():\n    return True"
  }
""",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file to edit.",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The exact text to find and replace. Must match exactly including whitespace.",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The replacement text.",
                    },
                },
                "required": ["file_path", "old_string", "new_string"],
            },
        )

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        file_path = args.get("file_path", "")
        old_string = args.get("old_string", "")
        new_string = args.get("new_string", "")

        if not file_path:
            return ToolResult(output="No file_path provided.", is_error=True)
        if not old_string:
            return ToolResult(
                output="No old_string provided. Specify the text to replace.",
                is_error=True,
            )
        if not new_string:
            return ToolResult(output="No new_string provided.", is_error=True)

        try:
            path = Path(file_path)
            content = path.read_text()
        except FileNotFoundError:
            return ToolResult(output=f"File not found: {file_path}", is_error=True)
        except OSError as e:
            return ToolResult(output=f"Error reading file: {e}", is_error=True)

        # Check if old_string exists in the file
        if old_string not in content:
            return ToolResult(
                output=f"old_string not found in file. Make sure the text matches exactly (including whitespace and newlines).",
                is_error=True,
            )

        # Perform the replacement
        new_content = content.replace(old_string, new_string, 1)  # Replace only first occurrence

        try:
            path.write_text(new_content)
        except OSError as e:
            return ToolResult(output=f"Error writing file: {e}", is_error=True)
        
        return ToolResult(output="Edit applied successfully.")


class MultiEditTool(Tool):
    """Multiple find-and-replace edits in a single file.
    
    Similar to EditTool but allows multiple replacements at once.
    """

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="multiedit",
            description="""
Make multiple find-and-replace edits to a file in a single operation.

Parameters:
- file_path: Absolute path to the file to edit.
- edits: Array of edit objects, each containing old_string and new_string.

Example usage:
  {
    "file_path": "/path/to/file.py",
    "edits": [
      {"old_string": "foo", "new_string": "bar"},
      {"old_string": "old_func", "new_string": "new_func"}
    ]
  }
""",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file to edit.",
                    },
                    "edits": {
                        "type": "array",
                        "description": "Array of edits to apply. Each edit has old_string and new_string.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "old_string": {
                                    "type": "string",
                                    "description": "Text to find.",
                                },
                                "new_string": {
                                    "type": "string",
                                    "description": "Replacement text.",
                                },
                            },
                            "required": ["old_string", "new_string"],
                        },
                    },
                },
                "required": ["file_path", "edits"],
            },
        )

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        file_path = args.get("file_path", "")
        edits = args.get("edits", [])

        if not file_path:
            return ToolResult(output="No file_path provided.", is_error=True)
        if not edits:
            return ToolResult(output="No edits provided.", is_error=True)

        try:
            path = Path(file_path)
            content = path.read_text()
        except FileNotFoundError:
            return ToolResult(output=f"File not found: {file_path}", is_error=True)
        except OSError as e:
            return ToolResult(output=f"Error reading file: {e}", is_error=True)

        # Apply all edits
        new_content = content
        for edit in edits:
            old_string = edit.get("old_string", "")
            new_string = edit.get("new_string", "")
            
            if not old_string:
                continue
                
            if old_string not in new_content:
                return ToolResult(
                    output=f"old_string not found: {repr(old_string[:50])}",
                    is_error=True,
                )
            
            new_content = new_content.replace(old_string, new_string, 1)

        try:
            path.write_text(new_content)
        except OSError as e:
            return ToolResult(output=f"Error writing file: {e}", is_error=True)

        return ToolResult(output=f"Applied {len(edits)} edit(s) successfully.")


class SearchWebTool(Tool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_web",
            description="Search the web using DuckDuckGo (no API key required).",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    }
                },
                "required": ["query"],
            },
        )

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "")
        if not query:
            return ToolResult(output="No query provided.", is_error=True)

        # Note: no_redirect=1 suppresses abstract text and related topics, so we don't use it
        url = f"https://api.duckduckgo.com/?q={query}&format=json"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

                results = []
                # Check both Abstract and AbstractText (API returns either depending on query)
                abstract = data.get("Abstract") or data.get("AbstractText")
                if abstract:
                    results.append(f"**Summary**: {abstract}")
                if data.get("Answer"):
                    results.append(f"**Answer**: {data['Answer']}")
                if data.get("RelatedTopics"):
                    for topic in data["RelatedTopics"][:3]:  # Limit to 3 topics
                        # API returns "Result" key, not "Text"
                        if "Result" in topic:
                            # Strip HTML tags from result
                            text = topic["Result"]
                            text = re.sub(r"<[^>]+>", "", text)
                            results.append(f"- {text}")
                        elif "Topics" in topic:
                            for subtopic in topic["Topics"][:2]:  # Limit to 2 subtopics
                                if "Result" in subtopic:
                                    text = subtopic["Result"]
                                    text = re.sub(r"<[^>]+>", "", text)
                                    results.append(f"- {text}")

                if not results:
                    return ToolResult(output="No results found.")

                return ToolResult(output="\n".join(results))
        except Exception as e:
            return ToolResult(output=f"Failed to search: {e}", is_error=True)


def default_tools() -> ToolRegistry:
    from .canvas_tool import CanvasTool

    registry = ToolRegistry()
    registry.register(BashTool())
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(EditTool())
    registry.register(MultiEditTool())
    registry.register(SearchWebTool())
    registry.register(CanvasTool())
    return registry
