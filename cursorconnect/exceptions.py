from typing import Optional, Any


class CursorAgentError(Exception):
    """
    Base exception for all CursorConnect SDK errors.

    This class serves as the root of the exception hierarchy. It provides
    common fields for error handling, such as whether the error is retryable
    and a specific error code.

    Parameters
    ----------
    message : str
        The error message describing what went wrong.
    is_retryable : bool, optional
        Whether the operation that caused this error can be safely retried.
        Defaults to False.
    code : str, optional
        A machine-readable error code provided by the API.
    cause : Exception, optional
        The underlying exception that triggered this error, if any.

    Attributes
    ----------
    message : str
        The error message.
    is_retryable : bool
        Indicates if the error is transient and retryable.
    code : Optional[str]
        A machine-readable error code.
    cause : Optional[Exception]
        The original exception.

    Examples
    --------
    >>> try:
    ...     raise CursorAgentError("Something went wrong", is_retryable=True)
    ... except CursorAgentError as e:
    ...     if e.is_retryable:
    ...         print("Retrying...")
    """

    def __init__(
        self,
        message: str,
        is_retryable: bool = False,
        code: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        self.message = message
        self.is_retryable = is_retryable
        self.code = code
        self.cause = cause
        super().__init__(message)


class AuthenticationError(CursorAgentError):
    """
    Raised when authentication fails or permissions are insufficient.

    This typically corresponds to HTTP 401 (Unauthorized) or 403 (Forbidden)
    status codes. It indicates that the provided credentials are invalid,
    expired, or do not have the necessary scopes.

    Examples
    --------
    >>> raise AuthenticationError("Invalid API key provided")
    """

    def __init__(
        self,
        message: str,
        is_retryable: bool = False,
        code: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message, is_retryable, code, cause)


class RateLimitError(CursorAgentError):
    """
    Raised when the API rate limit has been exceeded.

    Corresponds to HTTP 429 (Too Many Requests). This error is typically
    retryable after a certain delay.

    Examples
    --------
    >>> raise RateLimitError("Rate limit exceeded. Please wait 60 seconds.", is_retryable=True)
    """

    def __init__(
        self,
        message: str,
        is_retryable: bool = True,
        code: Optional[str] = "rate_limit_exceeded",
        cause: Optional[Exception] = None,
    ):
        super().__init__(message, is_retryable, code, cause)


class ConfigurationError(CursorAgentError):
    """
    Raised when there is an issue with the request configuration or parameters.

    Corresponds to HTTP 400 (Bad Request). This indicates that the client
    sent a request that the server could not understand or process.

    Examples
    --------
    >>> raise ConfigurationError("Missing required parameter: 'agent_id'")
    """

    def __init__(
        self,
        message: str,
        is_retryable: bool = False,
        code: Optional[str] = "invalid_request",
        cause: Optional[Exception] = None,
    ):
        super().__init__(message, is_retryable, code, cause)


class IntegrationNotConnectedError(ConfigurationError):
    """
    Raised when an operation requires a third-party integration that is not connected.

    This is a specific type of ConfigurationError that provides additional
    context about the missing integration.

    Parameters
    ----------
    message : str
        The error message.
    provider : str
        The name of the integration provider (e.g., 'github', 'slack').
    help_url : str
        A URL where the user can find instructions on how to connect the integration.
    is_retryable : bool, optional
        Defaults to False.
    code : str, optional
        Defaults to 'integration_not_connected'.
    cause : Exception, optional

    Attributes
    ----------
    provider : str
        The integration provider name.
    help_url : str
        The help documentation URL.

    Examples
    --------
    >>> raise IntegrationNotConnectedError(
    ...     "GitHub not connected",
    ...     provider="github",
    ...     help_url="https://docs.cursor.com/integrations/github"
    ... )
    """

    def __init__(
        self,
        message: str,
        provider: str,
        help_url: str,
        is_retryable: bool = False,
        code: Optional[str] = "integration_not_connected",
        cause: Optional[Exception] = None,
    ):
        self.provider = provider
        self.help_url = help_url
        super().__init__(message, is_retryable, code, cause)


class NetworkError(CursorAgentError):
    """
    Raised when a network-level error occurs.

    This includes timeouts, connection failures, or DNS issues. These errors
    are usually retryable.

    Examples
    --------
    >>> raise NetworkError("Connection timed out", is_retryable=True)
    """

    def __init__(
        self,
        message: str,
        is_retryable: bool = True,
        code: Optional[str] = "network_error",
        cause: Optional[Exception] = None,
    ):
        super().__init__(message, is_retryable, code, cause)


class UnsupportedRunOperationError(CursorAgentError):
    """
    Raised when an unsupported operation is attempted on an agent run.

    Parameters
    ----------
    message : str
        The error message.
    operation : str
        The name of the unsupported operation.
    is_retryable : bool, optional
        Defaults to False.
    code : str, optional
        Defaults to 'unsupported_operation'.
    cause : Exception, optional

    Attributes
    ----------
    operation : str
        The unsupported operation name.

    Examples
    --------
    >>> raise UnsupportedRunOperationError("Cannot cancel a completed run", operation="cancel")
    """

    def __init__(
        self,
        message: str,
        operation: str,
        is_retryable: bool = False,
        code: Optional[str] = "unsupported_operation",
        cause: Optional[Exception] = None,
    ):
        self.operation = operation
        super().__init__(message, is_retryable, code, cause)


class UnknownAgentError(CursorAgentError):
    """
    Raised when an unexpected error occurs on the server.

    Corresponds to HTTP 500 (Internal Server Error) or other unhandled
    status codes.

    Examples
    --------
    >>> raise UnknownAgentError("An unexpected error occurred on the server")
    """

    def __init__(
        self,
        message: str,
        is_retryable: bool = True,
        code: Optional[str] = "internal_error",
        cause: Optional[Exception] = None,
    ):
        super().__init__(message, is_retryable, code, cause)


def map_http_error(
    status_code: int,
    message: str,
    code: Optional[str] = None,
    cause: Optional[Exception] = None,
    **kwargs: Any,
) -> CursorAgentError:
    """
    Maps an HTTP status code to the appropriate CursorAgentError subclass.

    Parameters
    ----------
    status_code : int
        The HTTP status code returned by the API.
    message : str
        The error message from the API.
    code : str, optional
        The error code from the API.
    cause : Exception, optional
        The underlying exception.
    **kwargs : Any
        Additional context for specific error types (e.g., 'provider' and
        'help_url' for IntegrationNotConnectedError).

    Returns
    -------
    CursorAgentError
        An instance of a CursorAgentError subclass.

    Examples
    --------
    >>> err = map_http_error(401, "Invalid API key")
    >>> isinstance(err, AuthenticationError)
    True
    """
    if status_code in (401, 403):
        return AuthenticationError(message, is_retryable=False, code=code, cause=cause)
    elif status_code == 429:
        return RateLimitError(message, is_retryable=True, code=code, cause=cause)
    elif status_code == 400:
        if code == "integration_not_connected" and "provider" in kwargs and "help_url" in kwargs:
            return IntegrationNotConnectedError(
                message,
                provider=kwargs["provider"],
                help_url=kwargs["help_url"],
                is_retryable=False,
                code=code,
                cause=cause,
            )
        return ConfigurationError(message, is_retryable=False, code=code, cause=cause)
    elif status_code >= 500:
        return UnknownAgentError(message, is_retryable=True, code=code, cause=cause)
    else:
        return UnknownAgentError(
            f"Unexpected error (HTTP {status_code}): {message}",
            is_retryable=False,
            code=code,
            cause=cause,
        )

# Backward compatibility alias
CursorAPIError = CursorAgentError
