from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator

from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from .config import get_model, get_reasoning_effort, save_model_preferences
from .events import AgentEvent, EventType
from .exceptions import AgentError, AgentNotRunning
from .skills import LoadSkillsResult, format_skills_for_prompt, load_skills
from .system_prompt import SYSTEM_PROMPT
from .tools import ToolRegistry, default_tools

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "anthropic/claude-sonnet-4"
_DEFAULT_SYSTEM_PROMPT = SYSTEM_PROMPT

_MAX_RETRIES = 3
_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 30.0
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503}

_MODEL_CONTEXT_SIZES: dict[str, int] = {
    "anthropic/claude-sonnet-4": 200000,
    "mistralai/mistral-large-2512": 128000,
}

_COMPACTION_THRESHOLD = 0.8
_KEEP_RECENT_TOKENS = 20000
_CHARS_PER_TOKEN = 4


class AgentClient:
    """Async agent that streams LLM responses via OpenRouter and executes tools."""

    def __init__(
        self,
        model: str | None = None,
        system_prompt: str | None = None,
        tools: ToolRegistry | None = None,
        reasoning_effort: str = "xhigh",
        conversation_log_file: str | None = None,
        skills: LoadSkillsResult | None = None,
    ) -> None:
        # Use provided values first, then fall back to saved config
        self._model = model or get_model() or _DEFAULT_MODEL
        self._system_prompt_template = system_prompt or _DEFAULT_SYSTEM_PROMPT
        self._tools = tools or default_tools()
        self._client: AsyncOpenAI | None = None
        self._messages: list[dict[str, Any]] = []
        self._abort_event = asyncio.Event()
        self._steer_queue: asyncio.Queue[str] = asyncio.Queue()
        self._running = False
        self._reasoning_effort = get_reasoning_effort() or reasoning_effort
        self._conversation_log_file = conversation_log_file

        # Load skills and build system prompt
        self._skills_result = skills or load_skills()
        self._system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build system prompt with skills integrated."""
        prompt = self._system_prompt_template

        # Append skills if read tool is available
        if self._tools.get("read") is not None:
            skills_block = format_skills_for_prompt(self._skills_result.skills)
            if skills_block:
                prompt += skills_block

        return prompt

    @property
    def skills(self) -> LoadSkillsResult:
        """Return the loaded skills result."""
        return self._skills_result

    def reload_skills(self) -> None:
        """Reload skills from disk and rebuild system prompt."""
        self._skills_result = load_skills()
        self._system_prompt = self._build_system_prompt()
        logger.info("Reloaded %d skills", len(self._skills_result.skills))

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise AgentError("OPENROUTER_API_KEY environment variable is not set")
        self._client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            max_retries=0,
        )
        self._messages = []
        self._abort_event.clear()
        self._running = True
        logger.info("Agent started (model=%s)", self._model)

    async def stop(self) -> None:
        self._abort_event.set()
        if self._client:
            await self._client.close()
            self._client = None
        self._running = False
        logger.info("Agent stopped")

    async def prompt(self, message: str) -> AsyncIterator[AgentEvent]:
        if not self._running or self._client is None:
            raise AgentNotRunning("Agent is not running. Call start() first.")

        self._abort_event.clear()
        self._messages.append({"role": "user", "content": message})

        yield AgentEvent(type=EventType.TURN_START)

        while True:
            # Drain steer queue
            while not self._steer_queue.empty():
                try:
                    steer_msg = self._steer_queue.get_nowait()
                    self._messages.append({"role": "user", "content": steer_msg})
                except asyncio.QueueEmpty:
                    break

            if self._abort_event.is_set():
                yield AgentEvent(
                    type=EventType.TURN_END, context_info=self.context_info()
                )
                yield AgentEvent(type=EventType.AGENT_END)
                return

            # Auto-compact if approaching context limit
            if self._should_compact():
                yield AgentEvent(type=EventType.COMPACTION_START)
                try:
                    summary, tokens_before = await self._compact()
                    yield AgentEvent(
                        type=EventType.COMPACTION_END,
                        summary=summary,
                        tokens_before=tokens_before,
                    )
                except Exception as e:
                    logger.warning("Compaction failed: %s", e)
                    yield AgentEvent(
                        type=EventType.COMPACTION_END,
                        summary="",
                        tokens_before=0,
                        message=f"Compaction failed: {e}",
                    )

            # Call API with retry
            try:
                stream = await self._create_stream_with_retry()
            except AgentError as e:
                yield AgentEvent(type=EventType.ERROR, message=str(e))
                yield AgentEvent(type=EventType.AGENT_END)
                return

            # Stream response
            content_parts: list[str] = []
            tool_calls_by_index: dict[int, dict[str, Any]] = {}
            finish_reason = None

            try:
                async for chunk in stream:
                    if self._abort_event.is_set():
                        await stream.close()
                        yield AgentEvent(
                            type=EventType.TURN_END, context_info=self.context_info()
                        )
                        yield AgentEvent(type=EventType.AGENT_END)
                        return

                    choice = chunk.choices[0] if chunk.choices else None
                    if choice is None:
                        continue

                    delta = choice.delta
                    if delta.content:
                        content_parts.append(delta.content)
                        yield AgentEvent(type=EventType.TEXT_DELTA, delta=delta.content)

                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tool_calls_by_index:
                                tool_calls_by_index[idx] = {
                                    "id": tc_delta.id or "",
                                    "function": {"name": "", "arguments": ""},
                                }
                            tc = tool_calls_by_index[idx]
                            if tc_delta.id:
                                tc["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    tc["function"]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tc["function"][
                                        "arguments"
                                    ] += tc_delta.function.arguments

                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
            except (APIConnectionError, APIStatusError) as e:
                yield AgentEvent(type=EventType.ERROR, message=f"Stream error: {e}")
                yield AgentEvent(type=EventType.AGENT_END)
                return

            # Build assistant message
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            content_text = "".join(content_parts)
            if content_text:
                assistant_msg["content"] = content_text

            sorted_tool_calls = [
                tool_calls_by_index[i] for i in sorted(tool_calls_by_index)
            ]
            if sorted_tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": tc["function"],
                    }
                    for tc in sorted_tool_calls
                ]

            self._messages.append(assistant_msg)

            # If no tool calls, we're done
            if not sorted_tool_calls or finish_reason != "tool_calls":
                break

            # Execute tools
            for tc in sorted_tool_calls:
                if self._abort_event.is_set():
                    yield AgentEvent(
                        type=EventType.TURN_END, context_info=self.context_info()
                    )
                    yield AgentEvent(type=EventType.AGENT_END)
                    return

                func_name = tc["function"]["name"]
                call_id = tc["id"]
                try:
                    func_args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, TypeError):
                    func_args = {}

                yield AgentEvent(
                    type=EventType.TOOL_START,
                    tool_name=func_name,
                    tool_call_id=call_id,
                    args=func_args,
                )

                tool = self._tools.get(func_name)
                if tool is None:
                    result_text = f"Unknown tool: {func_name}"
                    is_error = True
                else:
                    try:
                        result = await tool.execute(func_args)
                        result_text = result.output
                        is_error = result.is_error
                    except Exception as e:
                        result_text = f"Tool execution error: {e}"
                        is_error = True

                yield AgentEvent(
                    type=EventType.TOOL_END,
                    tool_name=func_name,
                    tool_call_id=call_id,
                    result=result_text,
                    is_error=is_error,
                )

                self._messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result_text,
                    }
                )

            # Continue the loop for next turn
            yield AgentEvent(type=EventType.TURN_END, context_info=self.context_info())
            yield AgentEvent(type=EventType.TURN_START)

        yield AgentEvent(type=EventType.TURN_END, context_info=self.context_info())
        yield AgentEvent(type=EventType.AGENT_END)

    async def steer(self, message: str) -> AsyncIterator[AgentEvent]:
        """Steer the agent with a message or command (e.g., /compact)."""
        if message.strip() == "/compact":
            if not self._running or self._client is None:
                raise AgentNotRunning("Agent is not running. Call start() first.")
            yield AgentEvent(type=EventType.COMPACTION_START)
            try:
                summary, tokens_before = await self._compact()
                yield AgentEvent(
                    type=EventType.COMPACTION_END,
                    summary=summary,
                    tokens_before=tokens_before,
                )
            except Exception as e:
                logger.warning("Compaction failed: %s", e)
                yield AgentEvent(
                    type=EventType.COMPACTION_END,
                    summary="",
                    tokens_before=0,
                    message=f"Compaction failed: {e}",
                )
        elif message.strip() == "/model-info":
            if not self._running or self._client is None:
                raise AgentNotRunning("Agent is not running. Call start() first.")
            # Fetch model details from OpenRouter (cached to avoid repeated requests)
            model_details = await self._get_model_details(self._model)

            # Format model details as Markdown
            pricing = model_details.get("pricing", {})
            # OpenRouter returns price per token, convert to per 1M tokens
            prompt_cost = (
                float(pricing.get("prompt", 0)) * 1_000_000
                if pricing.get("prompt")
                else "N/A"
            )
            completion_cost = (
                float(pricing.get("completion", 0)) * 1_000_000
                if pricing.get("completion")
                else "N/A"
            )

            # Format with 2 decimal places
            prompt_cost_str = (
                f"{prompt_cost:.2f}"
                if isinstance(prompt_cost, (int, float))
                else prompt_cost
            )
            completion_cost_str = (
                f"{completion_cost:.2f}"
                if isinstance(completion_cost, (int, float))
                else completion_cost
            )

            markdown = f"""### Model Info

| Field               | Value                          |
|---------------------|--------------------------------|
| **Model ID**        | `{self._model}`                |
| **Name**            | {model_details.get("name", "N/A")} |
| **Description**      | {model_details.get("description", "N/A")} |
| **Context Window**   | {_MODEL_CONTEXT_SIZES.get(self._model, 128000)} tokens |
| **Prompt Cost**      | ${prompt_cost_str} per 1M tokens   |
| **Completion Cost**  | ${completion_cost_str} per 1M tokens |

#### Provider Info
| Field                     | Value                          |
|---------------------------|--------------------------------|
| **Max Completion Tokens** | {model_details.get("top_provider", {}).get("max_completion_tokens", "N/A")} |
| **Is Moderated**          | {model_details.get("top_provider", {}).get("is_moderated", "N/A")} |
"""

            model_info = {
                "model": self._model,
                "context_window": _MODEL_CONTEXT_SIZES.get(self._model, 128000),
                "details": model_details,
                "markdown": markdown,
            }
            yield AgentEvent(
                type=EventType.MODEL_INFO,
                model_info=model_info,
            )
        else:
            self._steer_queue.put_nowait(message)

    def context_info(self) -> dict[str, int]:
        """Return token estimates per category and total context window size."""
        system_chars = len(self._system_prompt)
        tools_chars = len(json.dumps(self._tools.schemas()))

        user_chars = 0
        assistant_chars = 0
        tool_chars = 0
        for msg in self._messages:
            serialized = len(json.dumps(msg))
            match msg.get("role"):
                case "user":
                    user_chars += serialized
                case "assistant":
                    assistant_chars += serialized
                case "tool":
                    tool_chars += serialized

        return {
            "system": system_chars // 4,
            "tools": tools_chars // 4,
            "user": user_chars // 4,
            "assistant": assistant_chars // 4,
            "tool_results": tool_chars // 4,
            "context_window": _MODEL_CONTEXT_SIZES.get(self._model, 128000),
        }

    def _estimate_tokens(self) -> int:
        total = len(self._system_prompt) + len(json.dumps(self._tools.schemas()))
        for msg in self._messages:
            total += len(json.dumps(msg))
        return total // _CHARS_PER_TOKEN

    def _should_compact(self) -> bool:
        context_window = _MODEL_CONTEXT_SIZES.get(self._model, 128000)
        return self._estimate_tokens() > int(context_window * _COMPACTION_THRESHOLD)

    def _find_cut_point(self) -> int:
        """Return index of first message to keep. Returns 0 if nothing to cut."""
        accumulated = 0
        cut_index = 0
        for i in range(len(self._messages) - 1, -1, -1):
            msg = self._messages[i]
            accumulated += len(json.dumps(msg)) // _CHARS_PER_TOKEN
            if accumulated >= _KEEP_RECENT_TOKENS:
                for j in range(i, len(self._messages)):
                    if self._messages[j]["role"] in ("user", "assistant"):
                        cut_index = j
                        break
                break
        return cut_index

    async def _compact(self) -> tuple[str, int]:
        """Summarize old messages and replace them. Returns (summary, tokens_before)."""
        tokens_before = self._estimate_tokens()
        cut = self._find_cut_point()
        if cut <= 0:
            return "(Nothing to compact — context is small enough)", tokens_before

        old_messages = self._messages[:cut]
        kept_messages = self._messages[cut:]

        summary_prompt = [
            {
                "role": "system",
                "content": (
                    "Summarize the following conversation history. "
                    "Cover: the user's goal, progress made, key decisions, "
                    "files read/modified, and what the next steps were. "
                    "Be concise but preserve all important context."
                ),
            },
            *old_messages,
            {"role": "user", "content": "Summarize the conversation so far."},
        ]

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=summary_prompt,
            stream=False,
        )
        summary = response.choices[0].message.content or "No summary generated."

        self._messages = [
            {"role": "user", "content": f"[Previous conversation summary]\n{summary}"},
            {
                "role": "assistant",
                "content": "Understood. I have the context from our previous conversation. How can I help?",
            },
            *kept_messages,
        ]

        return summary, tokens_before

    @property
    def model(self) -> str:
        return self._model

    @property
    def reasoning_effort(self) -> str:
        return self._reasoning_effort

    def set_reasoning_effort(self, effort: str) -> None:
        self._reasoning_effort = effort
        logger.info("Reasoning effort switched to %s", effort)
        save_model_preferences(self._model, effort)

    def set_model(self, model_id: str) -> None:
        self._model = model_id
        logger.info("Model switched to %s", model_id)
        save_model_preferences(model_id, self._reasoning_effort)

    async def abort(self) -> None:
        self._abort_event.set()

    async def _get_model_details(self, model_id: str) -> dict[str, Any]:
        """Fetch model details from OpenRouter, including pricing, description, and name."""
        if not hasattr(self, "_model_details_cache"):
            self._model_details_cache: dict[str, dict[str, Any]] = {}

        if model_id in self._model_details_cache:
            return self._model_details_cache[model_id]

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()

                for model in data.get("data", []):
                    self._model_details_cache[model["id"]] = {
                        "name": model.get("name", model["id"]),
                        "description": model.get(
                            "description", "No description available."
                        ),
                        "context_length": model.get("context_length"),
                        "pricing": model.get("pricing", {}),
                        "top_provider": model.get("top_provider", {}),
                    }

                return self._model_details_cache.get(model_id, {})
        except Exception as e:
            logger.warning("Failed to fetch model details: %s", e)
            return {
                "name": model_id,
                "description": "Failed to fetch model details.",
                "context_length": None,
                "pricing": {},
                "top_provider": {},
            }

    async def _create_stream_with_retry(self):
        """Create a streaming completion with exponential backoff retry."""
        backoff = _INITIAL_BACKOFF
        last_error: Exception | None = None

        # Build the request payload
        request_payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._system_prompt},
                *self._messages,
            ],
            "tools": self._tools.schemas() or None,
            "stream": True,
            "reasoning_effort": self._reasoning_effort,
        }

        # Log the request to file if conversation_log_file is set
        if self._conversation_log_file:
            try:
                with open(self._conversation_log_file, "a") as f:
                    f.write(
                        json.dumps({"type": "request", "payload": request_payload})
                        + "\n"
                    )
                logger.info("Logged request to %s", self._conversation_log_file)
            except OSError as e:
                logger.warning("Failed to write conversation log: %s", e)

        for attempt in range(_MAX_RETRIES):
            try:
                # Create the stream
                stream = await self._client.chat.completions.create(**request_payload)

                # If conversation_log_file is set, accumulate the full response
                if self._conversation_log_file:
                    response_chunks = []
                    async for chunk in stream:
                        # Extract the chunk data
                        chunk_dict = chunk.model_dump()
                        response_chunks.append(chunk_dict)
                    # Log the complete response after streaming is done
                    try:
                        with open(self._conversation_log_file, "a") as f:
                            f.write(
                                json.dumps(
                                    {"type": "response", "payload": response_chunks}
                                )
                                + "\n"
                            )
                    except OSError as e:
                        logger.warning("Failed to write conversation log: %s", e)
                    # Return a dummy stream for the rest of the code to iterate
                    return self._dummy_stream(response_chunks)
                else:
                    return stream

            except APIStatusError as e:
                last_error = e
                if e.status_code not in _RETRYABLE_STATUS_CODES:
                    raise AgentError(f"API error ({e.status_code}): {e.message}")
                logger.warning(
                    "Retryable API error (attempt %d/%d, status %d): %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    e.status_code,
                    e.message,
                )
            except APIConnectionError as e:
                last_error = e
                logger.warning(
                    "Connection error (attempt %d/%d): %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    e,
                )

            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF)

        raise AgentError(f"Max retries ({_MAX_RETRIES}) exceeded: {last_error}")

    async def _dummy_stream(self, chunks: list) -> AsyncIterator:
        """Yield pre-collected chunks as a dummy stream."""
        # Import here to avoid circular imports
        from openai.types.chat import ChatCompletionChunk

        for chunk_dict in chunks:
            yield ChatCompletionChunk(**chunk_dict)
