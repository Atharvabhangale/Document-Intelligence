"""Domain errors.

Every error that can reach an API client carries a stable machine-readable ``code``, a
user-safe ``message`` (never containing secrets, document text or stack traces), an HTTP status
and a ``retryable`` hint. The API layer maps these to a uniform JSON error body::

    {"error": {"code": "...", "message": "...", "retryable": false}}
"""

from __future__ import annotations


class DocIntelError(Exception):
    code: str = "internal_error"
    http_status: int = 500
    retryable: bool = False
    default_message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, details: dict | None = None) -> None:
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)


# --- Input / document errors ----------------------------------------------------------------


class InvalidRequestError(DocIntelError):
    code = "invalid_request"
    http_status = 400
    default_message = "The request is invalid."


class DocumentNotFoundError(DocIntelError):
    code = "document_not_found"
    http_status = 404
    default_message = "The document was not found."


class ReportNotFoundError(DocIntelError):
    code = "report_not_found"
    http_status = 404
    default_message = "No analysis exists for this document yet."


class UnsupportedMediaTypeError(DocIntelError):
    code = "unsupported_media_type"
    http_status = 415
    default_message = "Only PDF documents are supported in this version."


class DocumentTooLargeError(DocIntelError):
    code = "document_too_large"
    http_status = 413
    default_message = "The document exceeds the size supported by this version."


class ExtractionError(DocIntelError):
    code = "extraction_failed"
    http_status = 422
    default_message = "Text could not be extracted from the document."


class EncryptedDocumentError(ExtractionError):
    code = "document_encrypted"
    default_message = "The PDF is encrypted or password-protected and cannot be processed."


class NoExtractableTextError(ExtractionError):
    code = "no_extractable_text"
    default_message = (
        "The document has no extractable text layer (it may be a scanned image). "
        "OCR is not available in this version."
    )


# --- Windchill provider errors --------------------------------------------------------------


class WindchillProviderError(DocIntelError):
    code = "windchill_provider_error"
    http_status = 502
    retryable = True
    default_message = "The document source could not be reached."


class WindchillNotImplementedError(WindchillProviderError):
    code = "windchill_not_implemented"
    http_status = 501
    retryable = False
    default_message = "The real Windchill integration is not implemented yet."


class ContentNotAvailableError(WindchillProviderError):
    code = "content_not_available"
    http_status = 422
    retryable = False
    default_message = "The document has no supported primary content."


class AccessDeniedError(DocIntelError):
    code = "access_denied"
    http_status = 403
    default_message = "You do not have permission to access this document's content."


# --- AI errors ------------------------------------------------------------------------------


class AIProviderError(DocIntelError):
    code = "ai_provider_error"
    http_status = 502
    retryable = True
    default_message = "The AI service returned an error."


class AIRequestRejectedError(AIProviderError):
    """The AI service rejected the request itself (e.g. HTTP 400/413); retrying won't help."""

    code = "ai_request_rejected"
    http_status = 502
    retryable = False
    default_message = "The AI service rejected the request."


class AIConfigurationError(AIProviderError):
    code = "ai_not_configured"
    http_status = 503
    retryable = False
    default_message = "The AI provider is not configured."


class AIAuthenticationError(AIProviderError):
    code = "ai_authentication_failed"
    http_status = 503
    retryable = False
    default_message = "The AI service rejected the configured credentials."


class AIRateLimitError(AIProviderError):
    code = "ai_rate_limited"
    http_status = 429
    retryable = True
    default_message = "The AI service is busy. Please try again shortly."


class AITimeoutError(AIProviderError):
    code = "ai_timeout"
    http_status = 504
    retryable = True
    default_message = "The AI service did not respond in time."


class AIUnavailableError(AIProviderError):
    code = "ai_unavailable"
    http_status = 503
    retryable = True
    default_message = "The AI service is currently unavailable."


class AIRefusalError(AIProviderError):
    code = "ai_refused"
    http_status = 422
    retryable = False
    default_message = "The AI model declined to process this document."


class AIOutputTruncatedError(AIProviderError):
    code = "ai_output_truncated"
    http_status = 502
    retryable = True
    default_message = "The AI response was cut off before it was complete."


class AIOutputValidationError(AIProviderError):
    code = "ai_output_invalid"
    http_status = 502
    retryable = True
    default_message = (
        "The AI response could not be validated against the expected structure. "
        "No partial results are shown."
    )
