"""Database connection and session management using SQLAlchemy."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
import logging

from app.config import config

logger = logging.getLogger(__name__)

# Create base class for models
Base = declarative_base()

# Create engine with optimized connection pooling
if config.USE_LOCAL_DB:
    logger.info("Using local PostgreSQL database")
    engine = create_engine(
        config.DATABASE_URL,
        poolclass=QueuePool,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        connect_args={
            "connect_timeout": 5,
        },
        echo=False,
    )
else:
    logger.info("Using Railway PostgreSQL database")
    engine = create_engine(
        config.DATABASE_URL,
        poolclass=QueuePool,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=5,
        pool_recycle=3600,
        connect_args={
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000"
        },
        echo=False,
    )

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    Dependency function to get database session.
    Use this in FastAPI route dependencies.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session():
    """
    Context manager for database sessions.
    
    Usage:
        with get_db_session() as db:
            # Use db session
            pass
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Initialize database - create all tables."""
    logger.info("Initializing database...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully")
