import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase


def get_engine():
    try:
        url = st.secrets["DATABASE_URL"]
        url = "postgresql://postgres.nvrcdxuaadhrzzhcrrfo:TnCfceLMbIw25PN2@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres?sslmode=require"
    except Exception:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        url = os.environ.get("DATABASE_URL", "")

    if not url:
        st.error("DATABASE_URL is not set.")
        st.stop()

    # Normalise driver prefix
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # Strip any existing sslmode param then re-add cleanly
    if "sslmode" in url:
        import re
        url = re.sub(r"[?&]sslmode=[^&]*", "", url)

    connector = "&" if "?" in url else "?"
    url = f"{url}{connector}sslmode=require"

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
        connect_args={
            "sslmode": "require",
            "connect_timeout": 10,
        },
    )


engine     = get_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
