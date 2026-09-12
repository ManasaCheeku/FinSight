"""
FinSight — database engine, session factory, and Base.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import DATABASE_URL


# ──────────────────────────────────────────────
# Engine — SQLite with thread-safety for FastAPI
# ──────────────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ──────────────────────────────────────────────
# Declarative base for all ORM models
# ──────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ──────────────────────────────────────────────
# FastAPI dependency
# ──────────────────────────────────────────────
def get_db():
    """Yield a database session and close it when the request ends."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ──────────────────────────────────────────────
# DB initialisation helper
# ──────────────────────────────────────────────
def init_db():
    """Create all tables defined via Base metadata."""
    # Import models so SQLAlchemy picks them up before create_all
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
