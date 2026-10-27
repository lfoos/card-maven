"""RFC 9457 problem details. Every error response from the API uses this shape."""

from __future__ import annotations

from typing import Any

from flask import Flask, Response, g, jsonify
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

from card_maven.shared.errors import CardMavenError
from card_maven.shared.logging import get_logger

log = get_logger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"
_TYPE_BASE = "https://cardmaven.app/problems/"


def problem(
    status: int, code: str, title: str, detail: str | None = None, **extra: Any
) -> Response:
    body: dict[str, Any] = {
        "type": f"{_TYPE_BASE}{code}",
        "title": title,
        "status": status,
        "code": code,
    }
    if detail:
        body["detail"] = detail
    request_id = g.get("request_id")
    if request_id:
        body["request_id"] = request_id
    body.update(extra)
    response = jsonify(body)
    response.status_code = status
    response.content_type = PROBLEM_CONTENT_TYPE
    return response


def _field_errors(error: ValidationError) -> list[dict[str, str]]:
    errors = []
    for item in error.errors(include_url=False, include_input=False):
        loc = ".".join(str(part) for part in item["loc"]) or "body"
        message = item["msg"].removeprefix("Value error, ")
        errors.append({"loc": loc, "message": message})
    return errors


def validation_problem(error: ValidationError) -> Response:
    """Request or domain validation failure: 422 with per-field errors."""
    errors = _field_errors(error)
    detail = errors[0]["message"] if len(errors) == 1 else f"{len(errors)} fields are invalid"
    return problem(422, "invalid_input", "Invalid input", detail, errors=errors)


def register_problem_handlers(app: Flask) -> None:
    @app.errorhandler(CardMavenError)
    def _domain_error(error: CardMavenError) -> Response:
        if error.status >= 500:
            log.error("request_failed", code=error.code, detail=error.detail)
            # Server-side detail can contain internals; clients get the title.
            return problem(error.status, error.code, error.title)
        extra = dict(error.extra)
        field = extra.pop("field", None)
        if field and error.status == 422:
            # Same shape as request validation, so clients handle one format.
            extra["errors"] = [{"loc": field, "message": error.detail}]
        return problem(error.status, error.code, error.title, error.detail, **extra)

    @app.errorhandler(HTTPException)
    def _http_error(error: HTTPException) -> Response:
        status = error.code or 500
        code = (error.name or "error").lower().replace(" ", "_")
        response = problem(status, code, error.name or "Error", error.description)
        if status == 405 and error.response is None:
            allowed = getattr(error, "valid_methods", None)
            if allowed:
                response.headers["Allow"] = ", ".join(sorted(allowed))
        return response

    @app.errorhandler(Exception)
    def _unexpected(error: Exception) -> Response:
        log.exception("unhandled_exception", error_type=type(error).__name__)
        return problem(500, "internal_error", "Internal server error")
