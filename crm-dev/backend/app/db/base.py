# app/db/base.py
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData

# Единая naming convention для Alembic (устраняет дубли и нестабильные имена constraint'ов)
naming_convention = {
    "ix": "ix_%(table_name)s_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_label)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_label)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""
    metadata = MetaData(naming_convention=naming_convention)