from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
from websockets.asyncio.server import ServerConnection

from agent import AgentClient

from .protocol import ClientMessage, ProtocolError, context_info_message, error_message, serialize_event, user_message

logger = logging.getLogger(__name__)


class Session:
    """Binds connected WebSocket clients to a single agent instance.

    Serializes prompts (pi handles one at a time) and broadcasts
    agent events to all connected clients.
    """

    def __init__(self, agent: AgentClient) -> None:
        self.agent = agent
        self.clients: set[ServerConnection] = set()
        self._prompt_lock = asyncio.Lock()
        self._model_cache: list[dict[str, Any]] | None = None

    def add_client(self, ws: ServerConnection) -> None:
        self.clients.add(ws)
        logger.info("Client connected (%d total)", len(self.clients))

    def remove_client(self, ws: ServerConnection) -> None:
        self.clients.discard(ws)
        logger.info("Client disconnected (%d total)", len(self.clients))

    async def broadcast(self, message: str) -> None:
        logger.debug("Broadcast: %s", message)
        if not self.clients:
            return
        await asyncio.gather(
            *(ws.send(message) for ws in self.clients),
            return_exceptions=True,
        )

    async def handle_client_message(self, ws: ServerConnection, data: str) -> None:
        logger.debug("Client message: %s", data)
        try:
            msg = ClientMessage.from_json(data)
        except ProtocolError as e:
            await ws.send(error_message(str(e)))
            return

        match msg.type:
            case "prompt":
                await self._handle_prompt(msg.message)
            case "steer":
                stripped = msg.message.strip()
                if stripped.startswith("/model"):
                    await self._handle_model_command(stripped)
                elif stripped.startswith("/reasoning"):
                    await self._handle_reasoning_command(stripped)
                else:
                    logger.debug("Steer: %s", msg.message)
                    async for event in self.agent.steer(msg.message):
                        await self.broadcast(serialize_event(event))
            case "abort":
                logger.debug("Abort requested")
                await self.agent.abort()
            case "context_request":
                data = self.agent.context_info()
                await ws.send(context_info_message(data))
            case "model_list_request":
                models = await self._get_model_list()
                await ws.send(json.dumps({
                    "type": "model_list",
                    "models": models,
                    "current": self.agent.model,
                    "reasoning_effort": self.agent.reasoning_effort,
                }))
            case "model_info_request":
                await self._handle_model_info(msg.model_id)

    async def _handle_model_command(self, command: str) -> None:
        """Handle /model [model_id] — show or switch model."""
        parts = command.split(None, 1)
        if len(parts) < 2:
            await self.broadcast(json.dumps({"type": "model_set", "model": self.agent.model}))
            return
        model_id = parts[1].strip()
        self.agent.set_model(model_id)
        await self.broadcast(json.dumps({"type": "model_set", "model": model_id}))

    async def _handle_reasoning_command(self, command: str) -> None:
        """Handle /reasoning [effort] — show or switch reasoning effort."""
        VALID_EFFORTS = ["low", "medium", "high", "xhigh"]
        parts = command.split(None, 1)
        if len(parts) < 2:
            await self.broadcast(json.dumps({"type": "reasoning_effort_set", "effort": self.agent.reasoning_effort}))
            return
        effort = parts[1].strip().lower()
        if effort not in VALID_EFFORTS:
            await self.broadcast(json.dumps({
                "type": "reasoning_effort_set",
                "effort": self.agent.reasoning_effort,
                "error": f"Invalid effort. Valid values: {', '.join(VALID_EFFORTS)}",
            }))
            return
        self.agent.set_reasoning_effort(effort)
        await self.broadcast(json.dumps({"type": "reasoning_effort_set", "effort": effort}))

    async def _get_model_list(self) -> list[dict[str, str]]:
        """Fetch available models from OpenRouter (cached)."""
        if self._model_cache is not None:
            return self._model_cache
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://openrouter.ai/api/v1/models", timeout=10)
                resp.raise_for_status()
                data = resp.json()
                self._model_cache = [
                    {"id": m["id"], "name": m.get("name", m["id"]), "description": m.get("description", "")}
                    for m in data.get("data", [])
                ]
                logger.info("Fetched %d models from OpenRouter", len(self._model_cache))
                return self._model_cache
        except Exception as e:
            logger.warning("Failed to fetch model list: %s", e)
            return []

    async def _handle_model_info(self, model_id: str) -> None:
        """Fetch and display info about a specific model from OpenRouter."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://openrouter.ai/api/v1/models", timeout=10)
                resp.raise_for_status()
                data = resp.json()
                
                model_data = next((m for m in data.get("data", []) if m["id"] == model_id), None)
                if not model_data:
                    await self.broadcast(json.dumps({"type": "error", "message": f"Model not found: {model_id}"}))
                    return
                
                pricing = model_data.get("pricing", {})
                top_provider = model_data.get("top_provider", {})
                architecture = model_data.get("architecture", {})
                recommended = model_data.get("recommended", {})
                
                await self.broadcast(json.dumps({
                    "type": "model_info",
                    "model_id": model_data.get("id", model_id),
                    "name": model_data.get("name", model_id),
                    "description": model_data.get("description", ""),
                    "pricing": {
                        "prompt": pricing.get("prompt", "0"),
                        "completion": pricing.get("completion", "0"),
                    } if pricing else None,
                    "context_length": model_data.get("context_length", 0),
                    "top_provider": {
                        "provider": top_provider.get("provider_name", ""),
                        "max_completion_tokens": top_provider.get("max_completion_tokens", 0),
                        "supports_vision": top_provider.get("supports_vision", False),
                    } if top_provider else None,
                    "architecture": {
                        "model": architecture.get("model", ""),
                        "mode": architecture.get("mode", ""),
                        "tokenizer": architecture.get("tokenizer", ""),
                        "instruct_type": architecture.get("instruct_type", ""),
                    } if architecture else None,
                    "recommended": {
                        "prompt": recommended.get("prompt", 0),
                        "completion": recommended.get("completion", 0),
                    } if recommended else None,
                    "enabled": model_data.get("enabled", True),
                    "modality": model_data.get("modality", ""),
                    "created": model_data.get("created", 0),
                    "route": model_data.get("route", ""),
                }))
                logger.info("Fetched model info for %s", model_id)
        except Exception as e:
            logger.warning("Failed to fetch model info: %s", e)
            await self.broadcast(json.dumps({"type": "error", "message": f"Failed to fetch model info: {e}"}))

    async def _handle_prompt(self, message: str) -> None:
        # Broadcast user message to all clients so they stay in sync
        await self.broadcast(user_message(message))
        async with self._prompt_lock:
            try:
                async for event in self.agent.prompt(message):
                    await self.broadcast(serialize_event(event))
            except Exception as e:
                logger.exception("Error during prompt handling")
                await self.broadcast(error_message(str(e)))
