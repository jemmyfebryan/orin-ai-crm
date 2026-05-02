"""
API Tools Module

This module contains functions for making HTTP API calls to external services.
Uses httpx for async HTTP requests.
"""

import os
from typing import Optional
from datetime import datetime

import httpx

from src.orin_ai_crm.core.logger import get_logger

logger = get_logger(__name__)


async def reset_device_unit(device_id: int, api_token: str) -> dict:
    """
    Reset a device unit by calling the ORIN API reset endpoint.

    Args:
        device_id: The ID of the device to reset
        api_token: The Bearer token for authentication

    Returns:
        dict with:
            - success (bool): Whether the reset was successful
            - message (str): Success or error message
            - status_code (int): HTTP status code from API
            - error (str, optional): Error details if failed
    """
    logger.info(f"reset_device_unit called - device_id: {device_id}")

    # Get API URL from environment
    orin_api_url = os.getenv("ORIN_API_URL")

    if not orin_api_url:
        logger.error("ORIN_API_URL environment variable is not set!")
        return {
            'success': False,
            'message': 'Error: ORIN_API_URL is not configured',
            'status_code': None,
            'error': 'ORIN_API_URL environment variable not found'
        }

    # Construct the endpoint URL
    endpoint = f"{orin_api_url}/api/devices/{device_id}/reset_unit"
    logger.info(f"Calling reset endpoint: {endpoint}")

    # Prepare headers with Bearer token
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        # Make async POST request
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                endpoint,
                headers=headers
            )

            status_code = response.status_code
            logger.info(f"Reset API response status_code: {status_code}")

            # Determine success based on status code
            # 2xx status codes indicate success
            if 200 <= status_code < 300:
                logger.info(f"Device {device_id} reset successfully (status_code: {status_code})")
                return {
                    'success': True,
                    'message': 'Device reset successfully',
                    'status_code': status_code
                }
            else:
                # Handle error status codes
                error_msg = f"API returned error status code: {status_code}"

                # Try to get more details from response
                try:
                    response_data = response.json()
                    if isinstance(response_data, dict):
                        # Check for common error fields
                        if 'message' in response_data:
                            error_msg = f"API Error: {response_data['message']}"
                        elif 'error' in response_data:
                            error_msg = f"API Error: {response_data['error']}"
                        elif 'detail' in response_data:
                            error_msg = f"API Error: {response_data['detail']}"
                except:
                    # If response is not JSON, use status text
                    if response.text:
                        error_msg = f"API Error: {response.text[:200]}"

                logger.error(f"Failed to reset device {device_id}: {error_msg}")
                return {
                    'success': False,
                    'message': error_msg,
                    'status_code': status_code,
                    'error': error_msg
                }

    except httpx.TimeoutException as e:
        logger.error(f"Timeout while resetting device {device_id}: {str(e)}")
        return {
            'success': False,
            'message': 'Error: Request timeout - API took too long to respond',
            'status_code': None,
            'error': f'TimeoutException: {str(e)}'
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP status error while resetting device {device_id}: {str(e)}")
        return {
            'success': False,
            'message': f'Error: HTTP status error - {e.response.status_code}',
            'status_code': e.response.status_code,
            'error': f'HTTPStatusError: {str(e)}'
        }

    except httpx.ConnectError as e:
        logger.error(f"Connection error while resetting device {device_id}: {str(e)}")
        return {
            'success': False,
            'message': 'Error: Could not connect to API server',
            'status_code': None,
            'error': f'ConnectError: {str(e)}'
        }

    except Exception as e:
        logger.error(f"Unexpected error while resetting device {device_id}: {type(e).__name__}: {str(e)}")
        return {
            'success': False,
            'message': f'Error: Unexpected error occurred - {type(e).__name__}',
            'status_code': None,
            'error': f'{type(e).__name__}: {str(e)}'
        }
