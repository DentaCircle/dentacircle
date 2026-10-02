import os

import psycopg
import pytest

from dentacircle.core.database import to_psycopg_url

database_url = os.environ.get("DATABASE_URL")


@pytest.mark.skipif(database_url is None, reason="DATABASE_URL is not set")
def test_database_accepts_select_one() -> None:
    assert database_url is not None
    with psycopg.connect(to_psycopg_url(database_url), connect_timeout=5) as connection:
        row = connection.execute("SELECT 1").fetchone()
    assert row == (1,)
