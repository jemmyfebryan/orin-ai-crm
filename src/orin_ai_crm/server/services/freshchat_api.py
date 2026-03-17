"""
Freshchat API client service.
"""
import asyncio
import httpx

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.server.config.settings import settings

logger = get_logger(__name__)


async def send_message_to_freshchat(
    conversation_id: str,
    message_content: str,
    retry_count: int = 0
) -> bool:
    """
    Send a single message to Freshchat API with retry mechanism.

    Args:
        conversation_id: Freshchat conversation ID
        message_content: The message text to send
        retry_count: Current retry attempt number

    Returns:
        bool: True if successful, False otherwise
    """
    url = f"{settings.freshchat_url}/conversations/{conversation_id}/messages"

    payload = {
        "actor_type": "agent",
        "actor_id": settings.agent_id_bot,
        "message_type": "normal",
        "message_parts": [
            {
                "text": {
                    "content": message_content
                }
            }
        ]
    }

    headers = {
        "Authorization": f"Bearer {settings.freshchat_api_token}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                logger.info(f"Successfully sent message to Freshchat conversation {conversation_id}")
                return True
            else:
                logger.error(f"Failed to send message to Freshchat. Status: {response.status_code}, Response: {response.text}")

                # Retry with exponential backoff
                if retry_count < 3:
                    wait_time = 2 ** retry_count  # 1s, 2s, 4s
                    logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
                    await asyncio.sleep(wait_time)
                    return await send_message_to_freshchat(conversation_id, message_content, retry_count + 1)
                else:
                    logger.error(f"Max retry attempts reached for conversation {conversation_id}")
                    return False

    except httpx.TimeoutException:
        logger.error(f"Timeout while sending message to Freshchat for conversation {conversation_id}")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await send_message_to_freshchat(conversation_id, message_content, retry_count + 1)
        return False
    except Exception as e:
        logger.error(f"Error sending message to Freshchat: {str(e)}")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await send_message_to_freshchat(conversation_id, message_content, retry_count + 1)
        return False


async def get_freshchat_user_details(user_id: str) -> dict:
    """
    Fetch user details from Freshchat API to get phone number and other info.

    Args:
        user_id: Freshchat user ID

    Returns:
        User details dict with phone, first_name, etc. or None if failed
    """
    try:
        url = f"{settings.freshchat_url}/users/{user_id}"

        headers = {
            "Authorization": f"Bearer {settings.freshchat_api_token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)

            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"Fetched user details: phone={user_data.get('phone')}, first_name={user_data.get('first_name')}")
                return user_data
            else:
                logger.error(f"Failed to fetch user details: status={response.status_code}, body={response.text}")
                return None

    except Exception as e:
        logger.error(f"Error fetching Freshchat user details: {str(e)}")
        return None


async def send_image_to_freshchat(
    conversation_id: str,
    image_url: str,
    retry_count: int = 0
) -> bool:
    """
    Send an image message to Freshchat API with retry mechanism.

    Args:
        conversation_id: Freshchat conversation ID
        image_url: The URL of the image to send
        retry_count: Current retry attempt number

    Returns:
        bool: True if successful, False otherwise
    """
    url = f"{settings.freshchat_url}/conversations/{conversation_id}/messages"

    payload = {
        "actor_type": "agent",
        "actor_id": settings.agent_id_bot,
        "message_type": "normal",
        "message_parts": [
            {
                "image": {
                    "url": image_url
                }
            }
        ]
    }

    headers = {
        "Authorization": f"Bearer {settings.freshchat_api_token}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                logger.info(f"Successfully sent image to Freshchat conversation {conversation_id}: {image_url}")
                return True
            else:
                logger.error(f"Failed to send image to Freshchat. Status: {response.status_code}, Response: {response.text}")

                # Retry with exponential backoff
                if retry_count < 3:
                    wait_time = 2 ** retry_count  # 1s, 2s, 4s
                    logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
                    await asyncio.sleep(wait_time)
                    return await send_image_to_freshchat(conversation_id, image_url, retry_count + 1)
                else:
                    logger.error(f"Max retry attempts reached for image send to conversation {conversation_id}")
                    return False

    except httpx.TimeoutException:
        logger.error(f"Timeout while sending image to Freshchat for conversation {conversation_id}")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await send_image_to_freshchat(conversation_id, image_url, retry_count + 1)
        return False
    except Exception as e:
        logger.error(f"Error sending image to Freshchat: {str(e)}")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await send_image_to_freshchat(conversation_id, image_url, retry_count + 1)
        return False
