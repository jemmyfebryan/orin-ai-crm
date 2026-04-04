"""
Database retry utility for handling connection errors.

This module provides retry logic for database operations that may fail
due to connection issues, pool exhaustion, or network problems.

Common errors handled:
- "TCPTransport closed" - Connection was closed
- "Can't connect to MySQL server" - Network issues
- "Lost connection to MySQL server" - Connection timeout
- "Connection pool exhausted" - Too many connections
"""
import asyncio
import functools
import logging
from typing import Callable, TypeVar, ParamSpec
from sqlalchemy.exc import (
    SQLAlchemyError,
    DisconnectionError,
    OperationalError,
    InterfaceError,
    TimeoutError,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')
P = ParamSpec('P')


class DatabaseConnectionError(Exception):
    """Raised when database connection fails after retries."""
    pass


def retry_db_operation(
    max_retries: int = 3,
    base_delay: float = 0.5,
    backoff_factor: float = 2.0,
    raise_on_failure: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator to retry database operations with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 0.5)
        backoff_factor: Multiplier for delay after each retry (default: 2.0)
        raise_on_failure: Whether to raise exception after all retries (default: True)

    Returns:
        Decorated function that retries on connection errors

    Example:
        @retry_db_operation(max_retries=3)
        async def save_customer(data):
            async with AsyncSessionLocal() as db:
                # ... database operations ...
                pass
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception = None
            delay = base_delay

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (
                    DisconnectionError,
                    OperationalError,
                    InterfaceError,
                    TimeoutError,
                ) as e:
                    last_exception = e

                    # Check if this is a connection-related error
                    error_msg = str(e).lower()
                    is_connection_error = any(
                        keyword in error_msg
                        for keyword in [
                            "tcptransport closed",
                            "can't connect",
                            "lost connection",
                            "connection pool",
                            "mysql server has gone away",
                            "already closed",
                            "connection was closed",
                            "operational error",
                        ]
                    )

                    if not is_connection_error:
                        # Not a connection error, raise immediately
                        logger.error(f"Non-connection DB error in {func.__name__}: {str(e)}")
                        raise

                    # This is a connection error, retry
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"DB connection error in {func.__name__} "
                            f"(attempt {attempt + 1}/{max_retries}): {str(e)}\n"
                            f"Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(
                            f"DB connection failed in {func.__name__} after {max_retries} attempts: {str(e)}"
                        )

                except SQLAlchemyError as e:
                    # Other SQLAlchemy errors - don't retry, raise immediately
                    logger.error(f"SQLAlchemy error in {func.__name__}: {str(e)}")
                    raise

            # All retries exhausted
            if raise_on_failure and last_exception:
                raise DatabaseConnectionError(
                    f"Database operation failed after {max_retries} attempts: {str(last_exception)}"
                ) from last_exception

            # Return None or raise depending on configuration
            if raise_on_failure:
                raise DatabaseConnectionError(
                    f"Database operation failed after {max_retries} attempts"
                )
            return None  # type: ignore

        return wrapper
    return decorator


async def execute_with_retry(
    operation: Callable[..., T],
    *args: P.args,
    max_retries: int = 3,
    base_delay: float = 0.5,
    backoff_factor: float = 2.0,
    **kwargs: P.kwargs,
) -> T:
    """
    Execute a database operation with retry logic.

    Use this when you can't use the decorator (e.g., with inline functions).

    Args:
        operation: Async function to execute
        *args: Positional arguments for the operation
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay after each retry
        **kwargs: Keyword arguments for the operation

    Returns:
        Result of the operation

    Raises:
        DatabaseConnectionError: If all retries fail

    Example:
        result = await execute_with_retry(
            db.execute,
            select(Customer).where(Customer.id == customer_id)
        )
    """
    last_exception = None
    delay = base_delay

    for attempt in range(max_retries):
        try:
            return await operation(*args, **kwargs)
        except (
            DisconnectionError,
            OperationalError,
            InterfaceError,
            TimeoutError,
        ) as e:
            last_exception = e

            error_msg = str(e).lower()
            is_connection_error = any(
                keyword in error_msg
                for keyword in [
                    "tcptransport closed",
                    "can't connect",
                    "lost connection",
                    "connection pool",
                    "mysql server has gone away",
                    "already closed",
                    "connection was closed",
                ]
            )

            if not is_connection_error:
                raise

            if attempt < max_retries - 1:
                logger.warning(
                    f"DB connection error (attempt {attempt + 1}/{max_retries}): {str(e)}\n"
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
                delay *= backoff_factor
            else:
                logger.error(f"DB connection failed after {max_retries} attempts: {str(e)}")

    raise DatabaseConnectionError(
        f"Database operation failed after {max_retries} attempts: {str(last_exception)}"
    ) from last_exception
