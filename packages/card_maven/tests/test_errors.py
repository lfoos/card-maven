import pytest

from card_maven.shared import errors


@pytest.mark.parametrize(
    ("cls", "status", "code"),
    [
        (errors.CardMavenError, 500, "internal_error"),
        (errors.InvalidInputError, 422, "invalid_input"),
        (errors.NotFoundError, 404, "not_found"),
        (errors.ConflictError, 409, "conflict"),
        (errors.AuthenticationError, 401, "unauthenticated"),
        (errors.PermissionDeniedError, 403, "permission_denied"),
        (errors.DependencyUnavailableError, 503, "dependency_unavailable"),
    ],
)
def test_status_and_code(cls: type[errors.CardMavenError], status: int, code: str) -> None:
    error = cls()
    assert error.status == status
    assert error.code == code
    assert error.detail == cls.title


def test_detail_and_extra() -> None:
    error = errors.InvalidInputError("bad year", field="year")
    assert str(error) == "bad year"
    assert error.extra == {"field": "year"}


def test_only_dependency_errors_are_retryable() -> None:
    assert errors.DependencyUnavailableError.retryable
    assert not errors.InvalidInputError.retryable
