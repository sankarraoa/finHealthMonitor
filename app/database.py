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
# Different settings for local vs Railway PostgreSQL
if config.USE_LOCAL_DB:
    # Local PostgreSQL: More connections, faster timeouts, better performance
    logger.info("Using local PostgreSQL database")
    engine = create_engine(
        config.DATABASE_URL,
        poolclass=QueuePool,
        pool_pre_ping=True,
        pool_size=10,  # More connections for local development
        max_overflow=20,  # More overflow for local development
        pool_recycle=3600,  # Recycle connections after 1 hour
        connect_args={
            "connect_timeout": 5,  # Faster timeout for local
        },
        echo=False,  # Set to True for SQL query logging during development
    )
else:
    # Railway PostgreSQL: Optimized for remote connection with latency
    logger.info("Using Railway PostgreSQL database")
    engine = create_engine(
        config.DATABASE_URL,
        poolclass=QueuePool,  # Use QueuePool for better connection management
        pool_pre_ping=True,  # Verify connections before using
        pool_size=3,  # Reduced from 10 - Railway free tier doesn't need many connections
        max_overflow=5,  # Reduced from 20 - additional connections beyond pool_size
        pool_recycle=3600,  # Recycle connections after 1 hour to prevent stale connections
        connect_args={
            "connect_timeout": 10,  # 10 second connection timeout
            "options": "-c statement_timeout=30000"  # 30 second query timeout
        },
        echo=False,  # Set to True for SQL query logging (disable in production)
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
    Reuses sessions within a request context to reduce connection overhead.
    
    Usage:
        with get_db_session() as db:
            # Use db session
            pass
        # Session is automatically committed/rolled back and closed
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
