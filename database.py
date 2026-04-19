import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import re


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
        pool_pre_ping=True,       # test connection before using it
        pool_size=3,              # keep max 3 persistent connections
        max_overflow=2,           # allow 2 extra under load
        pool_timeout=10,          # wait max 10s for a connection
        pool_recycle=300,         # recycle connections every 5 minutes
        connect_args={
            "sslmode":        "require",
            "connect_timeout": 10,
        },
    )


engine       = get_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Use as a context manager: with get_db() as db:"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
