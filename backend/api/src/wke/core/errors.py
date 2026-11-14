"""RFC 9457 problem+json error type shared by every layer; no web framework."""

from __future__ import annotations

from wke.core.models import ErrorCode, TopicCandidate

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_BASE_URI = "https://wke.piotrkrzysztof.dev/problems"


class ApiException(Exception):
    """An expected failure that must be rendered as problem+json.

    Args:
        status_code: HTTP status to respond with.
        code: machine-readable ApiError.code.
        detail: human-readable detail, omitted from the body if None.
        retry_after: seconds to wait before retrying, sets Retry-After.
        candidates: disambiguation candidates (code == "disambiguation" only).
    """

    # Declared on the class so readers see the literal set, never a widened str.
    code: ErrorCode

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        detail: str | None = None,
        retry_after: int | None = None,
        candidates: list[TopicCandidate] | None = None,
    ) -> None:
        super().__init__(detail or code)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.retry_after = retry_after
        self.candidates = candidates
