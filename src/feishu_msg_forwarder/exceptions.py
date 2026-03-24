class ForwarderError(Exception):
    """Base error for the project."""


class ConfigError(ForwarderError):
    """Raised when configuration is invalid."""


class AuthError(ForwarderError):
    """Raised when authentication fails."""


class ApiError(ForwarderError):
    """Raised when a Feishu API call fails."""


class RetryableApiError(ApiError):
    """Raised when an API error can be retried."""
