"""Entry points must register every ORM table before touching the database.

Foreign keys cross bounded contexts (e.g. market_sync_job.requested_by ->
app_user), so a process that imported only some model modules fails at its
first flush. The test suite imports everything, which hides this; so check in
a fresh interpreter.
"""

import subprocess
import sys

import pytest


@pytest.mark.parametrize("module", ["card_maven_workers.cli", "card_maven_api.app"])
def test_entrypoint_registers_all_tables(module: str) -> None:
    before = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import {module}\nfrom card_maven.shared.db import Base\n"
            "print(len(Base.metadata.tables))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    full = subprocess.run(
        [
            sys.executable,
            "-c",
            "import card_maven.models\nfrom card_maven.shared.db import Base\n"
            "print(len(Base.metadata.tables))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert before.stdout == full.stdout
