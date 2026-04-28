"""
Freshchat API client service.
"""
import asyncio
import httpx
from typing import Optional

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.server.config.settings import settings
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_agent_name

logger = get_logger(__name__)


async def send_message_to_freshchat(
    conversation_id: str,
    message_content: str,
    customer_id: Optional[int] = None,
    save_to_db: bool = True,
    retry_count: int = 0
) -> bool:
    """
    Send a single message to Freshchat API with retry mechanism.

    Args:
        conversation_id: Freshchat conversation ID
        message_content: The message text to send
        customer_id: Optional customer ID for database save
        save_to_db: Whether to save the message to database (default: True)
        retry_count: Current retry attempt number

    Returns:
        bool: True if successful, False otherwise
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import save_message_to_db

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

                # Save to database if customer_id is provided and save_to_db is True
                if customer_id and save_to_db:
                    await save_message_to_db(customer_id, "ai", message_content, content_type="text")
                    logger.debug(f"Saved message to DB for customer_id={customer_id}: {message_content[:50]}...")

                return True
            else:
                logger.error(f"Failed to send message to Freshchat. Status: {response.status_code}, Response: {response.text}")

                # Retry with exponential backoff
                if retry_count < 3:
                    wait_time = 2 ** retry_count  # 1s, 2s, 4s
                    logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
                    await asyncio.sleep(wait_time)
                    return await send_message_to_freshchat(conversation_id, message_content, customer_id, save_to_db, retry_count + 1)
                else:
                    logger.error(f"Max retry attempts reached for conversation {conversation_id}")
                    return False

    except httpx.TimeoutException:
        logger.error(f"Timeout while sending message to Freshchat for conversation {conversation_id}")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await send_message_to_freshchat(conversation_id, message_content, customer_id, save_to_db, retry_count + 1)
        return False
    except Exception as e:
        logger.error(f"Error sending message to Freshchat: {str(e)}")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await send_message_to_freshchat(conversation_id, message_content, customer_id, save_to_db, retry_count + 1)
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
    customer_id: Optional[int] = None,
    save_to_db: bool = True,
    retry_count: int = 0
) -> bool:
    """
    Send an image message to Freshchat API with retry mechanism.

    Args:
        conversation_id: Freshchat conversation ID
        image_url: The URL of the image to send
        customer_id: Optional customer ID for database save
        save_to_db: Whether to save the message to database (default: True)
        retry_count: Current retry attempt number

    Returns:
        bool: True if successful, False otherwise
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import save_message_to_db

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

                # Save to database if customer_id is provided and save_to_db is True
                if customer_id and save_to_db:
                    await save_message_to_db(customer_id, "ai", image_url, content_type="image")
                    logger.debug(f"Saved image to DB for customer_id={customer_id}: {image_url}")

                return True
            else:
                logger.error(f"Failed to send image to Freshchat. Status: {response.status_code}, Response: {response.text}")

                # Retry with exponential backoff
                if retry_count < 3:
                    wait_time = 2 ** retry_count  # 1s, 2s, 4s
                    logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
                    await asyncio.sleep(wait_time)
                    return await send_image_to_freshchat(conversation_id, image_url, customer_id, save_to_db, retry_count + 1)
                else:
                    logger.error(f"Max retry attempts reached for image send to conversation {conversation_id}")
                    return False

    except httpx.TimeoutException:
        logger.error(f"Timeout while sending image to Freshchat for conversation {conversation_id}")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await send_image_to_freshchat(conversation_id, image_url, customer_id, save_to_db, retry_count + 1)
        return False
    except Exception as e:
        logger.error(f"Error sending image to Freshchat: {str(e)}")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await send_image_to_freshchat(conversation_id, image_url, customer_id, save_to_db, retry_count + 1)
        return False


async def send_pdf_to_freshchat(
    conversation_id: str,
    pdf_url: str,
    customer_id: Optional[int] = None,
    save_to_db: bool = True,
    retry_count: int = 0
) -> bool:
    """
    Send a PDF file message to Freshchat API with retry mechanism.

    Args:
        conversation_id: Freshchat conversation ID
        pdf_url: The URL of the PDF file to send
        customer_id: Optional customer ID for database save
        save_to_db: Whether to save the message to database (default: True)
        retry_count: Current retry attempt number

    Returns:
        bool: True if successful, False otherwise
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import save_message_to_db

    url = f"{settings.freshchat_url}/conversations/{conversation_id}/messages"

    payload = {
        "actor_type": "agent",
        "actor_id": settings.agent_id_bot,
        "message_type": "normal",
        "message_parts": [
            {
                "file": {
                    "url": pdf_url,
                    "content_type": "application/pdf"
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
                logger.info(f"Successfully sent PDF to Freshchat conversation {conversation_id}: {pdf_url}")

                # Save to database if customer_id is provided and save_to_db is True
                if customer_id and save_to_db:
                    await save_message_to_db(customer_id, "ai", pdf_url, content_type="pdf")
                    logger.debug(f"Saved PDF to DB for customer_id={customer_id}: {pdf_url}")

                return True
            else:
                logger.error(f"Failed to send PDF to Freshchat. Status: {response.status_code}, Response: {response.text}")

                # Retry with exponential backoff
                if retry_count < 3:
                    wait_time = 2 ** retry_count  # 1s, 2s, 4s
                    logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
                    await asyncio.sleep(wait_time)
                    return await send_pdf_to_freshchat(conversation_id, pdf_url, customer_id, save_to_db, retry_count + 1)
                else:
                    logger.error(f"Max retry attempts reached for PDF send to conversation {conversation_id}")
                    return False

    except httpx.TimeoutException:
        logger.error(f"Timeout while sending PDF to Freshchat for conversation {conversation_id}")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await send_pdf_to_freshchat(conversation_id, pdf_url, customer_id, save_to_db, retry_count + 1)
        return False
    except Exception as e:
        logger.error(f"Error sending PDF to Freshchat: {str(e)}")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await send_pdf_to_freshchat(conversation_id, pdf_url, customer_id, save_to_db, retry_count + 1)
        return False


async def notify_live_agent_takeover(
    customer_name: str,
    customer_phone: str,
    retry_count: int = 0
) -> bool:
    """
    Send notification to live agent when human takeover is triggered.

    Args:
        customer_name: Customer's name
        customer_phone: Customer's phone number
        retry_count: Current retry attempt number

    Returns:
        bool: True if successful, False otherwise
    """
    # Get agent name from database (sync function, no await needed)
    agent_name = get_agent_name()

    # Format the message
    if customer_name:
        notify_message = f"{agent_name} dimatikan untuk customer Kak {customer_name} ({customer_phone}), mohon Live Agent untuk segera mengambil alih sesi pesan!"
    else:
        notify_message = f"{agent_name} dimatikan untuk customer dengan nomor {customer_phone}, mohon Live Agent untuk segera mengambil alih sesi pesan!"

    # Check if live agent alert configuration is complete
    if not settings.live_agent_alert_endpoint or not settings.live_agent_alert_to or not settings.live_agent_alert_api_key:
        logger.warning("Live agent alert configuration incomplete (missing LIVE_AGENT_ALERT_ENDPOINT, LIVE_AGENT_ALERT_TO, or LIVE_AGENT_ALERT_API_KEY), skipping live agent notification")
        return False

    # Send message to live agent alert endpoint
    logger.info(f"Sending takeover notification to live agent for customer: {customer_name} ({customer_phone})")

    url = f"{settings.live_agent_alert_endpoint}/sendText"
    payload = {
        "args": {
            "to": settings.live_agent_alert_to,
            "content": notify_message
        }
    }
    headers = {
        "api_key": settings.live_agent_alert_api_key,
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                logger.info(f"✅ Takeover notification sent successfully to live agent")
                return True
            else:
                logger.error(f"Failed to send takeover notification. Status: {response.status_code}, Response: {response.text}")

                # Retry with exponential backoff
                if retry_count < 3:
                    wait_time = 2 ** retry_count  # 1s, 2s, 4s
                    logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
                    await asyncio.sleep(wait_time)
                    return await notify_live_agent_takeover(customer_name, customer_phone, retry_count + 1)
                else:
                    logger.error(f"Max retry attempts reached for takeover notification")
                    return False

    except httpx.TimeoutException:
        logger.error(f"Timeout while sending takeover notification to live agent")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await notify_live_agent_takeover(customer_name, customer_phone, retry_count + 1)
        return False
    except Exception as e:
        logger.error(f"Error sending takeover notification: {str(e)}")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await notify_live_agent_takeover(customer_name, customer_phone, retry_count + 1)
        return False


async def notify_live_agent_release(
    customer_name: str,
    customer_phone: str,
    retry_count: int = 0
) -> bool:
    """
    Send notification to live agent when human takeover is released (AI takes back over).

    Args:
        customer_name: Customer's name
        customer_phone: Customer's phone number
        retry_count: Current retry attempt number

    Returns:
        bool: True if successful, False otherwise
    """
    # Get agent name from database (sync function, no await needed)
    agent_name = get_agent_name()

    # Format the message
    if customer_name:
        notify_message = f"{agent_name} kembali dihidupkan untuk customer Kak {customer_name} ({customer_phone})!"
    else:
        notify_message = f"{agent_name} kembali dihidupkan untuk customer dengan nomor {customer_phone}!"

    # Check if live agent alert configuration is complete
    if not settings.live_agent_alert_endpoint or not settings.live_agent_alert_to or not settings.live_agent_alert_api_key:
        logger.warning("Live agent alert configuration incomplete (missing LIVE_AGENT_ALERT_ENDPOINT, LIVE_AGENT_ALERT_TO, or LIVE_AGENT_ALERT_API_KEY), skipping live agent notification")
        return False

    # Send message to live agent alert endpoint
    logger.info(f"Sending release notification to live agent for customer: {customer_name} ({customer_phone})")

    url = f"{settings.live_agent_alert_endpoint}/sendText"
    payload = {
        "args": {
            "to": settings.live_agent_alert_to,
            "content": notify_message
        }
    }
    headers = {
        "api_key": settings.live_agent_alert_api_key,
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                logger.info(f"✅ Release notification sent successfully to live agent")
                return True
            else:
                logger.error(f"Failed to send release notification. Status: {response.status_code}, Response: {response.text}")

                # Retry with exponential backoff
                if retry_count < 3:
                    wait_time = 2 ** retry_count  # 1s, 2s, 4s
                    logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
                    await asyncio.sleep(wait_time)
                    return await notify_live_agent_release(customer_name, customer_phone, retry_count + 1)
                else:
                    logger.error(f"Max retry attempts reached for release notification")
                    return False

    except httpx.TimeoutException:
        logger.error(f"Timeout while sending release notification to live agent")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await notify_live_agent_release(customer_name, customer_phone, retry_count + 1)
        return False
    except Exception as e:
        logger.error(f"Error sending release notification: {str(e)}")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await notify_live_agent_release(customer_name, customer_phone, retry_count + 1)
        return False

