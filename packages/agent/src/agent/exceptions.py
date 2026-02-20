class AgentError(Exception):
    """Base exception for agent errors."""


class AgentNotRunning(AgentError):
    """Raised when attempting to use an agent that isn't running."""


# Backwards-compatible alias
ProcessNotRunning = AgentNotRunning
