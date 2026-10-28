"""analytics/dbt/bin/dbt-from-url: database URL -> dbt connection variables."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "analytics/dbt/bin/dbt-from-url"


@pytest.fixture(scope="module")
def script() -> ModuleType:
    from importlib.machinery import SourceFileLoader

    loader = SourceFileLoader("dbt_from_url", str(SCRIPT))
    spec = importlib.util.spec_from_loader("dbt_from_url", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_splits_a_full_url(script: ModuleType) -> None:
    env = script.connection_env(
        "postgresql+psycopg://card%40maven:p%3Ass@db.internal:6543/cards?sslmode=require"
    )
    assert env == {
        "DBT_PG_HOST": "db.internal",
        "DBT_PG_PORT": "6543",
        "DBT_PG_USER": "card@maven",
        "DBT_PG_PASSWORD": "p:ss",
        "DBT_PG_DATABASE": "cards",
        "DBT_PG_SSLMODE": "require",
    }


def test_defaults(script: ModuleType) -> None:
    env = script.connection_env("postgresql://u@/cards")
    assert (env["DBT_PG_HOST"], env["DBT_PG_PORT"], env["DBT_PG_PASSWORD"]) == (
        "localhost",
        "5432",
        "",
    )
    assert "DBT_PG_SSLMODE" not in env


def test_rejects_other_databases(script: ModuleType) -> None:
    with pytest.raises(SystemExit, match="postgresql"):
        script.connection_env("mysql://u:p@h/db")


def test_execs_dbt_with_derived_env(script: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[str]]] = []
    for key in ("HOST", "PORT", "USER", "PASSWORD", "DATABASE", "SSLMODE"):
        monkeypatch.delenv(f"DBT_PG_{key}", raising=False)  # restored after the test
    monkeypatch.setenv("CARD_MAVEN_DATABASE_URL", "postgresql://u:p@h:5432/d")
    monkeypatch.setattr(script.os, "execvp", lambda file, args: calls.append((file, args)))
    monkeypatch.setattr(script.sys, "argv", ["dbt-from-url", "build", "--fail-fast"])
    script.main()
    assert calls == [("dbt", ["dbt", "build", "--fail-fast"])]
    assert script.os.environ["DBT_PG_HOST"] == "h"
