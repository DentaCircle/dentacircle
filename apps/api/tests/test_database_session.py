from sqlalchemy import text
from sqlalchemy.orm import Session

from dentacircle.core.database import NAMING_CONVENTION, Base, to_sqlalchemy_url
from tests.support import rollback_session


def test_base_uses_the_naming_convention() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    assert NAMING_CONVENTION["pk"] == "pk_%(table_name)s"


def test_db_session_can_query(db_session: Session) -> None:
    assert db_session.execute(text("SELECT 1")).scalar_one() == 1


def test_session_rolls_back_committed_work(throwaway_database_url: str) -> None:
    with rollback_session(throwaway_database_url) as session:
        session.execute(text("CREATE TABLE probe_rollback (id integer)"))
        session.execute(text("INSERT INTO probe_rollback (id) VALUES (1)"))
        session.commit()

    from sqlalchemy import create_engine

    engine = create_engine(
        to_sqlalchemy_url(throwaway_database_url),
        connect_args={"connect_timeout": 5},
    )
    with engine.connect() as connection:
        exists: str | None = connection.execute(
            text("SELECT to_regclass('public.probe_rollback')")
        ).scalar_one()
    engine.dispose()
    assert exists is None
