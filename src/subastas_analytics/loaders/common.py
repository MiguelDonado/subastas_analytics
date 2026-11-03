"""Helpers shared by the loaders of each layer."""

from ..config import SQL_DIR


def read_sql(filename: str) -> str:
    """Reads a sql file into memory"""
    return (SQL_DIR / filename).read_text()
