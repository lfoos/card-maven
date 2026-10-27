"""OpenAPI metadata shared by every blueprint, and the spec export entry point.

Regenerate the checked-in contract with ``make openapi``. A test fails if
``contracts/openapi.json`` drifts from the code.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from flask_openapi3.models.info import Info
from flask_openapi3.types import ResponseDict

from card_maven_api.schemas import ProblemOut, ValidationProblemOut

INFO = Info(
    title="Card Maven API",
    version="1.0.0",
    description="Track a sports card collection and value it against the market. "
    "Errors are RFC 9457 problem+json.",
)
SECURITY_SCHEMES: dict[str, Any] = {
    "bearer": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
}
BEARER: list[dict[str, list[str]]] = [{"bearer": []}]
PROTECTED_RESPONSES: ResponseDict = {
    401: ProblemOut,
    422: ValidationProblemOut,
    429: ProblemOut,
}
NOT_FOUND: ResponseDict = {404: ProblemOut}


def spec_json() -> str:
    from card_maven.shared.config import Settings
    from card_maven.shared.storage.memory import InMemoryObjectStore
    from card_maven_api.app import create_app

    app = create_app(
        Settings(_env_file=None, environment="test", rate_limits_enabled=False),
        object_store=InMemoryObjectStore(),
    )
    return json.dumps(app.api_doc, indent=2, sort_keys=True) + "\n"


def write_spec() -> None:
    """``make openapi``: print the spec to stdout."""
    sys.stdout.write(spec_json())
