"""Unit tests for AgentEvent.to_dict() serialization."""

from agent.events import AgentEvent, EventType


class TestAgentEventToDict:
    def test_turn_start(self):
        event = AgentEvent(type=EventType.TURN_START)
        assert event.to_dict() == {"type": "turn_start"}

    def test_text_delta(self):
        event = AgentEvent(type=EventType.TEXT_DELTA, delta="hi")
        assert event.to_dict() == {"type": "text_delta", "delta": "hi"}

    def test_tool_start(self):
        event = AgentEvent(
            type=EventType.TOOL_START,
            tool_name="bash",
            tool_call_id="tc_1",
            args={"cmd": "ls"},
        )
        d = event.to_dict()
        assert d["type"] == "tool_start"
        assert d["tool_name"] == "bash"
        assert d["tool_call_id"] == "tc_1"
        assert d["args"] == {"cmd": "ls"}

    def test_tool_update(self):
        event = AgentEvent(
            type=EventType.TOOL_UPDATE,
            tool_call_id="tc_1",
            tool_name="bash",
            partial_result="output",
        )
        d = event.to_dict()
        assert d["type"] == "tool_update"
        assert d["partial_result"] == "output"

    def test_tool_end(self):
        event = AgentEvent(
            type=EventType.TOOL_END,
            tool_call_id="tc_1",
            tool_name="bash",
            result="done",
            is_error=False,
        )
        d = event.to_dict()
        assert d["type"] == "tool_end"
        assert d["result"] == "done"
        assert d["is_error"] is False

    def test_turn_end(self):
        assert AgentEvent(type=EventType.TURN_END).to_dict() == {"type": "turn_end"}

    def test_agent_end(self):
        assert AgentEvent(type=EventType.AGENT_END).to_dict() == {"type": "agent_end"}

    def test_error(self):
        event = AgentEvent(type=EventType.ERROR, message="fail")
        assert event.to_dict() == {"type": "error", "message": "fail"}
