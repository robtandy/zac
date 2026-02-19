"""Custom exceptions for the action system."""


class ActionSystemError(Exception):
    """Base exception for action system errors."""


class HandlerNotFoundError(ActionSystemError):
    """Raised when a handler is not registered."""

    def __init__(self, handler_id: str) -> None:
        super().__init__(f"Handler not found: {handler_id}")
        self.handler_id = handler_id


class ActionNotFoundError(ActionSystemError):
    """Raised when an action is not found."""

    def __init__(self, action_id: str) -> None:
        super().__init__(f"Action not found: {action_id}")
        self.action_id = action_id


class PermissionNotFoundError(ActionSystemError):
    """Raised when a permission is not defined."""

    def __init__(self, permission_name: str) -> None:
        super().__init__(f"Permission not defined: {permission_name}")
        self.permission_name = permission_name


class HandlerExecutionError(ActionSystemError):
    """Raised when a handler fails to execute an action."""

    def __init__(self, handler_id: str, action_name: str, reason: str) -> None:
        super().__init__(f"Handler {handler_id} failed on {action_name}: {reason}")
        self.handler_id = handler_id
        self.action_name = action_name
        self.reason = reason
