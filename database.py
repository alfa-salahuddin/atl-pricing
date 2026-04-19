import re
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from contextlib import contextmanager


def get_engine():
    try:
        url = st.secrets["DATABASE_URL"]
    except Exception:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        url = os.environ.get("DATABASE_URL", "")

    if not url:
        st.error("DATABASE_URL is not set.")
        st.stop()

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    if "sslmode" in url:
        url = re.sub(r"[?&]sslmode=[^&]*", "", url)

    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}sslmode=require"

    return create_engine(
        url,
        pool_pre_ping=True,    # test each connection before use
        pool_size=3,           # max 3 persistent connections
        max_overflow=2,        # 2 extra allowed under burst load
        pool_timeout=15,       # wait up to 15s for a free connection
        pool_recycle=180,      # recycle connections every 3 minutes
        connect_args={
            "sslmode":         "require",
            "connect_timeout": 10,
        },
    )


engine       = get_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def get_db():
    """
    Safe context manager — always closes the session.
    Usage:
        with get_db() as db:
            results = db.query(...)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
