import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
def get_engine():
    """
    Reads DATABASE_URL from Streamlit secrets (production)
    or falls back to a local .env / environment variable for dev use.
    Supabase requires sslmode=require — added automatically if missing.
    """
    try:
        url = st.secrets["DATABASE_URL"]
    except Exception:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        url = os.environ.get("DATABASE_URL", "")

    if not url:
        st.error("DATABASE_URL is not set. Add it to Streamlit secrets or a local .env file.")
        st.stop()

    # Supabase requires SSL — append sslmode=require if not already in the URL
    if "sslmode" not in url:
        separator = "&" if "?" in url else "?"
        url = url + separator + "sslmode=require"

    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"sslmode": "require"},
    )


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ---------------------------------------------------------------------------
# Base class for all models
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Dependency helper — use in every page
# ---------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
