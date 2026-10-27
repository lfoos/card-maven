"""Liveness and readiness probes (used by Kubernetes and load balancers)."""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from card_maven.shared.logging import get_logger
from card_maven_api.extensions import api_context
from card_maven_api.problems import problem

log = get_logger(__name__)
bp = Blueprint("health", __name__)


@bp.get("/healthz")
def liveness() -> Response:
    """The process is up. Never touches dependencies, so it can't cause restart loops."""
    return jsonify(status="ok")


@bp.get("/readyz")
def readiness() -> Response:
    """The process can serve traffic: the database answers."""
    try:
        with api_context(current_app).session_factory() as session:
            session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        log.warning("readiness_check_failed", dependency="database", error=type(exc).__name__)
        return problem(503, "not_ready", "Service not ready", "database is unavailable")
    return jsonify(status="ready", checks={"database": "ok"})
