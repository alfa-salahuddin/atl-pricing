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

    return create_engine(url, pool_pre_ping=True)


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
