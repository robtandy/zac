# Edit/read tools inspired by pi-mono
#
# This implementation follows the pi-mono coding-agent approach:
# - Edit: find and replace exact text (with fuzzy matching for minor whitespace differences)
# - Read: offset/limit with truncation

import asyncio
import difflib
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    output: str
    is_error: bool = False
    # For edit tool - contains the diff and first changed line
    diff: str | None = None
    first_changed_line: int | None = None


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

# Default truncation limits (matching pi-mono's truncate.ts)
DEFAULT_MAX_LINES = 500
DEFAULT_MAX_BYTES = 100 * 1024  # 100KB


# === Fuzzy matching and diff utilities (from pi-mono) ===

def normalize_to_lf(text: str) -> str:
    """Normalize line endings to LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def detect_line_ending(content: str) -> str:
    """Detect the line ending used in content."""
    crlf_idx = content.find("\r\n")
    lf_idx = content.find("\n")
    if lf_idx == -1:
        return "\n"
    if crlf_idx == -1:
        return "\n"
    return "\r\n" if crlf_idx < lf_idx else "\n"


def restore_line_endings(text: str, ending: str) -> str:
    """Restore line endings to the original format."""
    if ending == "\r\n":
        return text.replace("\n", "\r\n")
    return text


def normalize_for_fuzzy_match(text: str) -> str:
    """
    Normalize text for fuzzy matching. Applies progressive transformations:
    - Strip trailing whitespace from each line
    - Normalize smart quotes to ASCII equivalents
    - Normalize Unicode dashes/hyphens to ASCII hyphen
    - Normalize special Unicode spaces to regular space
    """
    result = text
    # Strip trailing whitespace per line
    result = "\n".join(line.rstrip() for line in result.split("\n"))
    # Smart single quotes → '
    result = re.sub(r"[\u2018\u2019\u201A\u201B]", "'", result)
    # Smart double quotes → "
    result = re.sub(r"[\u201C\u201D\u201E\u201F]", '"', result)
    # Various dashes/hyphens → -
    result = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", result)
    # Special spaces → regular space
    result = re.sub(r"[\u00A0\u2002-\u200A\u202F\u205F\u3000]", " ", result)
    return result


def fuzzy_find_text(content: str, old_text: str) -> tuple[bool, int, int, str]:
    """
    Find oldText in content, trying exact match first, then fuzzy match.
    Returns: (found, index, match_length, content_for_replacement)
    """
    # Try exact match first
    exact_index = content.find(old_text)
    if exact_index != -1:
        return (True, exact_index, len(old_text), content)

    # Try fuzzy match
    fuzzy_content = normalize_for_fuzzy_match(content)
    fuzzy_old_text = normalize_for_fuzzy_match(old_text)
    fuzzy_index = fuzzy_content.find(fuzzy_old_text)

    if fuzzy_index == -1:
        return (False, -1, 0, content)

    return (True, fuzzy_index, len(fuzzy_old_text), fuzzy_content)


def generate_diff_string(old_content: str, new_content: str, context_lines: int = 4) -> tuple[str, int | None]:
    """
    Generate a unified diff string with line numbers and context.
    Returns: (diff_string, first_changed_line)
    """
    old_lines = old_content.split("\n")
    new_lines = new_content.split("\n")

    # Use Python's difflib
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        lineterm="",
        n=context_lines,
    )

    output: list[str] = []
    old_line_num = 1
    new_line_num = 1
    first_changed_line: int | None = None

    for line in diff:
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            # Parse the hunk header to get line numbers
            match = re.match(r"@@ -(\d+),?\d* \+(\d+),?\d* @@", line)
            if match:
                old_line_num = int(match.group(1))
                new_line_num = int(match.group(2))
            output.append(line)
        elif line.startswith("+"):
            if first_changed_line is None:
                first_changed_line = new_line_num
            output.append(f"{new_line_num:4d} {line}")
            new_line_num += 1
        elif line.startswith("-"):
            if first_changed_line is None:
                first_changed_line = new_line_num
            output.append(f"{old_line_num:4d} {line}")
            old_line_num += 1
        else:
            output.append(f"{old_line_num:4d} {line}")
            old_line_num += 1
            new_line_num += 1

    return ("\n".join(output), first_changed_line)


def strip_bom(content: str) -> tuple[str, str]:
    """Strip UTF-8 BOM if present. Returns (bom, text_without_bom)."""
    if content.startswith("\ufeff"):
        return ("\ufeff", content[1:])
    return ("", content)


# === Truncation utilities ===

def format_size(bytes_count: int) -> str:
    """Format bytes as human-readable size."""
    if bytes_count < 1024:
        return f"{bytes_count}B"
    elif bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f}KB"
    else:
        return f"{bytes_count / (1024 * 1024):.1f}MB"


def truncate_head(
    content: str,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[str, bool, str | None, int, int]:
    """
    Truncate content from the head (keep first N lines/bytes).
    Returns: (truncated_content, was_truncated, truncated_by_reason, total_lines, output_lines)
    """
    total_bytes = len(content.encode("utf-8"))
    lines = content.split("\n")
    total_lines = len(lines)

    # Check if no truncation needed
    if total_lines <= max_lines and total_bytes <= max_bytes:
        return (content, False, None, total_lines, total_lines)

    # Check if first line alone exceeds byte limit
    first_line_bytes = len(lines[0].encode("utf-8"))
    if first_line_bytes > max_bytes:
        return ("", True, "first_line_exceeds_limit", total_lines, 0)

    # Collect complete lines that fit
    output_lines: list[str] = []
    output_bytes_count = 0
    truncated_by: str | None = None

    for i, line in enumerate(lines):
        if i >= max_lines:
            truncated_by = "lines"
            break

        line_bytes = len(line.encode("utf-8")) + (1 if i > 0 else 0)  # +1 for newline

        if output_bytes_count + line_bytes > max_bytes:
            truncated_by = "bytes"
            break

        output_lines.append(line)
        output_bytes_count += line_bytes

    output_content = "\n".join(output_lines)
    return (output_content, truncated_by is not None, truncated_by, total_lines, len(output_lines))


# === Tool implementations ===

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
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read",
            description=f"""Read the contents of a file. Output is truncated to {DEFAULT_MAX_LINES} lines or {format_size(DEFAULT_MAX_BYTES)} (whichever is hit first). Use offset/limit for large files.""",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read (relative or absolute).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (1-indexed).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to read.",
                    },
                },
                "required": ["path"],
            },
        )

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", "")
        offset = args.get("offset")  # 1-indexed, optional
        limit = args.get("limit")  # optional

        if not path:
            return ToolResult(output="No path provided.", is_error=True)

        try:
            file_path = Path(path)
            raw_content = file_path.read_text()
        except FileNotFoundError:
            return ToolResult(output=f"File not found: {path}", is_error=True)
        except OSError as e:
            return ToolResult(output=f"Error reading file: {e}", is_error=True)

        # Strip BOM before processing
        _, content = strip_bom(raw_content)

        # Normalize line endings
        original_ending = detect_line_ending(content)
        content = normalize_to_lf(content)

        all_lines = content.split("\n")
        total_file_lines = len(all_lines)

        # Apply offset (1-indexed to 0-indexed)
        start_line = (offset - 1) if offset else 0
        start_line = max(0, start_line)

        # Check if offset is out of bounds
        if start_line >= total_file_lines:
            return ToolResult(
                output=f"Offset {offset} is beyond end of file ({total_file_lines} lines total)",
                is_error=True,
            )

        # Get the content to truncate
        if limit is not None:
            end_line = min(start_line + limit, total_file_lines)
            selected_content = "\n".join(all_lines[start_line:end_line])
            user_limited_lines = end_line - start_line
        else:
            selected_content = "\n".join(all_lines[start_line:])
            user_limited_lines = None

        # Apply truncation
        (
            truncated_content,
            was_truncated,
            truncated_reason,
            total_lines,
            output_lines,
        ) = truncate_head(selected_content)

        start_line_display = start_line + 1  # For display (1-indexed)

        if was_truncated and truncated_reason == "first_line_exceeds_limit":
            first_line_size = format_size(len(all_lines[start_line].encode("utf-8")))
            output = f"[Line {start_line_display} is {first_line_size}, exceeds {format_size(DEFAULT_MAX_BYTES)} limit. Use bash: sed -n '{start_line_display}p' {path} | head -c {DEFAULT_MAX_BYTES}]"
        elif was_truncated:
            end_line_display = start_line_display + output_lines - 1
            next_offset = end_line_display + 1

            output = truncated_content
            if truncated_reason == "lines":
                output += f"\n\n[Showing lines {start_line_display}-{end_line_display} of {total_file_lines}. Use offset={next_offset} to continue.]"
            else:
                output += f"\n\n[Showing lines {start_line_display}-{end_line_display} of {total_file_lines} ({format_size(DEFAULT_MAX_BYTES)} limit). Use offset={next_offset} to continue.]"
        elif user_limited_lines is not None and start_line + user_limited_lines < total_file_lines:
            # User specified limit, there's more content, but no truncation
            remaining = total_file_lines - (start_line + user_limited_lines)
            next_offset = start_line + user_limited_lines + 1

            output = truncated_content
            output += f"\n\n[{remaining} more lines in file. Use offset={next_offset} to continue.]"
        else:
            output = truncated_content

        return ToolResult(output=output)


class WriteTool(Tool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write",
            description="Write content to a file. Creates parent directories if needed.",
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
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="edit",
            description="""
Edit a file by replacing exact text. The oldText must match exactly (including whitespace). Uses fuzzy matching to handle minor differences in whitespace, quotes, and dashes.

Parameters:
- path: Path to the file to edit (relative or absolute)
- oldText: Exact text to find and replace
- newText: New text to replace the old text with

The tool returns a diff of the changes made.
""",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to edit (relative or absolute).",
                    },
                    "oldText": {
                        "type": "string",
                        "description": "Exact text to find and replace (must match exactly).",
                    },
                    "newText": {
                        "type": "string",
                        "description": "New text to replace the old text with.",
                    },
                },
                "required": ["path", "oldText", "newText"],
            },
        )

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", "")
        old_text = args.get("oldText", "")
        new_text = args.get("newText", "")

        if not path:
            return ToolResult(output="No path provided.", is_error=True)
        if not old_text:
            return ToolResult(output="No oldText provided.", is_error=True)
        if not new_text:
            return ToolResult(output="No newText provided.", is_error=True)

        try:
            file_path = Path(path)
            raw_content = file_path.read_text()
        except FileNotFoundError:
            return ToolResult(output=f"File not found: {path}", is_error=True)
        except OSError as e:
            return ToolResult(output=f"Error reading file: {e}", is_error=True)

        # Strip BOM before matching
        bom, content = strip_bom(raw_content)

        # Normalize line endings
        original_ending = detect_line_ending(content)
        normalized_content = normalize_to_lf(content)
        normalized_old_text = normalize_to_lf(old_text)
        normalized_new_text = normalize_to_lf(new_text)

        # Find the old text using fuzzy matching
        found, match_index, match_length, content_for_replacement = fuzzy_find_text(
            normalized_content, normalized_old_text
        )

        if not found:
            return ToolResult(
                output=f"Could not find the exact text in {path}. The old text must match exactly including all whitespace and newlines.",
                is_error=True,
            )

        # Count occurrences using fuzzy-normalized content
        fuzzy_content = normalize_for_fuzzy_match(normalized_content)
        fuzzy_old_text = normalize_for_fuzzy_match(normalized_old_text)
        occurrences = fuzzy_content.count(fuzzy_old_text)

        if occurrences > 1:
            return ToolResult(
                output=f"Found {occurrences} occurrences of the text in {path}. The text must be unique. Please provide more context to make it unique.",
                is_error=True,
            )

        # Perform replacement
        new_content = (
            content_for_replacement[:match_index]
            + normalized_new_text
            + content_for_replacement[match_index + match_length:]
        )

        # Verify the replacement actually changed something
        if content_for_replacement == new_content:
            return ToolResult(
                output=f"No changes made to {path}. The replacement produced identical content. This might indicate an issue with special characters or the text not existing as expected.",
                is_error=True,
            )

        # Restore original line endings
        final_content = restore_line_endings(new_content, original_ending)
        final_content = bom + final_content

        try:
            file_path.write_text(final_content)
        except OSError as e:
            return ToolResult(output=f"Error writing file: {e}", is_error=True)

        # Generate diff
        diff_string, first_changed_line = generate_diff_string(
            content_for_replacement, new_content
        )

        return ToolResult(
            output=f"Successfully replaced text in {path}.",
            diff=diff_string,
            first_changed_line=first_changed_line,
        )


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

        url = f"https://api.duckduckgo.com/?q={query}&format=json"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

                results: list[str] = []
                abstract = data.get("Abstract") or data.get("AbstractText")
                if abstract:
                    results.append(f"**Summary**: {abstract}")
                if data.get("Answer"):
                    results.append(f"**Answer**: {data['Answer']}")
                if data.get("RelatedTopics"):
                    for topic in data["RelatedTopics"][:3]:
                        if "Result" in topic:
                            text = topic["Result"]
                            text = re.sub(r"<[^>]+>", "", text)
                            results.append(f"- {text}")
                        elif "Topics" in topic:
                            for subtopic in topic["Topics"][:2]:
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
    registry.register(SearchWebTool())
    registry.register(CanvasTool())
    return registry
