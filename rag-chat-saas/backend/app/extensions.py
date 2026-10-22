from __future__ import annotations

from pathlib import Path

from flask import Flask
from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker


class Database:
    def __init__(self) -> None:
        self.engine = None
        self.session = None

    def init_app(self, app: Flask) -> None:
        path = Path(app.config["DATABASE_PATH"])
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{path.as_posix()}", future=True)

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        self.session = scoped_session(sessionmaker(bind=self.engine, expire_on_commit=False))
        app.teardown_appcontext(lambda _error: self.session.remove())

    def create_all(self) -> None:
        from app.models import Base

        Base.metadata.create_all(self.engine)


database = Database()
