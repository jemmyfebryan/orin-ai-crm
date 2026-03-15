"""
Authentication and authorization utilities.
"""
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.server.config.settings import settings

logger = get_logger(__name__)
security = HTTPBearer()


async def verify_bearer_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Verify Bearer token for /freshchat-agent endpoint.

    Args:
        credentials: HTTP Bearer credentials from Authorization header

    Returns:
        str: The verified token

    Raises:
        HTTPException: If token is invalid
    """
    if credentials.credentials != settings.freshchat_agent_bearer_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials
