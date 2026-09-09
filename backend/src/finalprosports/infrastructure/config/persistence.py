"""SQLAlchemy engine/session factory.

pgvector's psycopg adapter is registered on EVERY connection: the query vector then travels as a typed binary `vector`
parameter instead of text. Measured on this corpus: `ORDER BY embedding <=> CAST(:text_param AS vector)` costs ~46 ms because
Postgres re-parses the 768-float text for every row (the cast of a parameter is not folded), the typed parameter ~2 ms."""
from pgvector.psycopg import register_vector
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def make_session_factory(database_url: str):
    engine = create_engine(database_url, pool_pre_ping=True, future=True)

    @event.listens_for(engine, "connect")
    def _register_pgvector(dbapi_connection, _record):
        register_vector(dbapi_connection)

    return sessionmaker(bind=engine, expire_on_commit=False)
