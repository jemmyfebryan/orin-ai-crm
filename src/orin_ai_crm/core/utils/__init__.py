"""
Utility modules for the CRM application.

This package contains reusable utilities and helpers.
"""
from .db_retry import retry_db_operation, execute_with_retry, DatabaseConnectionError
from .phone_utils import (
    normalize_indonesian_phone_number,
    generate_phone_number_variations,
    build_phone_number_sql_conditions
)

__all__ = [
    "retry_db_operation",
    "execute_with_retry",
    "DatabaseConnectionError",
    "normalize_indonesian_phone_number",
    "generate_phone_number_variations",
    "build_phone_number_sql_conditions",
]
