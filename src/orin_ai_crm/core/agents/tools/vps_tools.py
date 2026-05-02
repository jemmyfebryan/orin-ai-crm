"""
VPS Database Tools - Query external VPS database for vehicle data
"""

import os
from typing import Optional, List
from dotenv import load_dotenv
import httpx
from sqlalchemy import select

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.utils.phone_utils import build_phone_number_sql_conditions

logger = get_logger(__name__)

# Load environment variables
load_dotenv()

VPS_IP = os.getenv("VPS_IP")
VPS_DB_PORT = os.getenv("VPS_DB_PORT", "8080")  # Default port if not specified
VPS_API_URL = f"http://{VPS_IP}:{VPS_DB_PORT}/mysql/devsites_orin"


async def query_vps_db(sql_query: str) -> Optional[dict]:
    """
    Query the VPS database via API.

    Args:
        sql_query: SQL query string

    Returns:
        Dictionary with response data or None if error
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                VPS_API_URL,
                json={"query": sql_query}
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"VPS DB query successful: {sql_query[:50]}...")
            return data
    except httpx.HTTPError as e:
        logger.error(f"VPS DB query failed: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"VPS DB query error: {str(e)}")
        return None


async def search_vehicle_by_name(vehicle_name: str) -> tuple[Optional[int], list[dict]]:
    """
    Search for vehicle by name in VPS database and return its ID.

    Args:
        vehicle_name: Vehicle name to search for (e.g., "CRF", "Avanza", "XMAX", "ioniq 6")

    Returns:
        Tuple of (vehicle_id, all_matches)
        - vehicle_id: ID if exact match found, None if multiple/no matches
        - all_matches: List of all matching vehicles from VPS DB
    """
    logger.info(f"search_vehicle_by_name called - vehicle_name: {vehicle_name}")

    if not vehicle_name or len(vehicle_name.strip()) < 2:
        logger.info(f"Invalid vehicle_name: '{vehicle_name}' - returning (None, [])")
        return None, []

    # Try multiple search strategies in order
    search_attempts = [
        vehicle_name.strip(),  # Original with leading/trailing spaces removed
        vehicle_name.strip().replace(" ", ""),  # Remove all spaces (e.g., "ioniq 6" → "ioniq6")
        vehicle_name.strip().replace("-", "").replace(" ", "").replace(".", ""),  # Remove common separators
    ]

    # Try each search variation until we find results
    for clean_name in search_attempts:
        if not clean_name or len(clean_name) < 2:
            continue

        logger.info(f"Searching for vehicle with: '{clean_name}'")

        # Search using LIKE query (case-insensitive)
        sql_query = f"SELECT id, name FROM vehicles WHERE LOWER(name) LIKE LOWER('%{clean_name}%') ORDER BY name ASC"

        result = await query_vps_db(sql_query)

        if not result:
            logger.warning(f"VPS DB returned invalid result for vehicle: {clean_name}")
            continue

        # VPS DB API returns data in "rows" key, not "data" key
        vehicles = result.get("rows", [])

        if vehicles and len(vehicles) > 0:
            logger.info(f"VPS DB returned {len(vehicles)} vehicles for '{clean_name}': {[v.get('name') for v in vehicles]}")

            # Check if we have exact match (compare cleaned versions)
            exact_match = None
            clean_search = clean_name.lower().replace(" ", "").replace("-", "").replace(".", "")
            for vehicle in vehicles:
                v_name = vehicle.get("name", "").lower().replace(" ", "").replace("-", "").replace(".", "")
                if v_name == clean_search:
                    exact_match = vehicle
                    break

            if exact_match:
                vehicle_id = exact_match.get("id")
                logger.info(f"EXACT match found: '{exact_match.get('name')}' (ID: {vehicle_id}) for search: '{vehicle_name}' → '{clean_name}'")
                return vehicle_id, vehicles

            # Multiple partial matches found (or single partial match)
            logger.info(f"PARTIAL matches found: {len(vehicles)} vehicles matching '{clean_name}' - returning (None, matches)")
            return None, vehicles

    # No results found with any search variation
    logger.warning(f"No vehicles found for '{vehicle_name}' with any search variation")
    return None, []


async def get_vehicle_by_id(vehicle_id: int) -> Optional[dict]:
    """
    Get vehicle information by ID from VPS database.

    Args:
        vehicle_id: Vehicle ID

    Returns:
        Vehicle dict with id and name, or None if not found
    """
    logger.info(f"get_vehicle_by_id called - vehicle_id: {vehicle_id}")

    if vehicle_id <= 0:
        logger.info(f"Invalid vehicle_id: {vehicle_id}")
        return None

    sql_query = f"SELECT id, name FROM vehicles WHERE id = {vehicle_id} LIMIT 1"

    result = await query_vps_db(sql_query)

    if not result:
        logger.warning(f"VPS DB returned invalid result for vehicle_id: {vehicle_id}")
        return None

    # VPS DB API returns data in "rows" key
    vehicles = result.get("rows", [])

    if not vehicles or len(vehicles) == 0:
        logger.info(f"No vehicle found with ID: {vehicle_id}")
        return None

    vehicle = vehicles[0]
    logger.info(f"Vehicle found: {vehicle}")
    return vehicle


async def get_all_vehicles() -> List[dict]:
    """
    Get all vehicles from VPS database.

    Returns:
        List of vehicle dicts with id and name
    """
    logger.info("get_all_vehicles called")

    sql_query = "SELECT id, name FROM vehicles ORDER BY name ASC"

    result = await query_vps_db(sql_query)

    if not result:
        logger.warning("VPS DB returned invalid result for all vehicles")
        return []

    # VPS DB API returns data in "rows" key
    vehicles = result.get("rows", [])
    logger.info(f"Retrieved {len(vehicles)} vehicles from VPS DB")
    return vehicles


async def get_account_type_from_vps(phone_number: str) -> Optional[dict]:
    """
    Get user's account type from VPS database by phone number.

    Args:
        phone_number: Customer's phone number (can be in various formats)

    Returns:
        dict with:
            - account_type: 'free', 'basic', 'premium' (mapped to 'plus'), 'lite', 'promo', or None if not found
            - account_expired_date: Expiration date string or None
        Returns None if user not found
    """
    logger.info(f"get_account_type_from_vps called - phone_number: {phone_number}")

    if not phone_number:
        logger.warning("Empty phone_number provided")
        return None

    # Generate phone number variations for matching
    variations = []

    # Original format
    clean_phone = phone_number.strip()
    variations.append(f"'{clean_phone}'")

    # Generate variations based on the format
    if clean_phone.startswith('+'):
        # +6285123456789 -> 6285123456789, 085123456789
        without_plus = clean_phone[1:]  # Remove +
        variations.append(f"'{without_plus}'")
        if without_plus.startswith('62'):
            with_zero = '0' + without_plus[2:]  # 62 -> 0
            variations.append(f"'{with_zero}'")
    elif clean_phone.startswith('62'):
        # 6285123456789 -> +6285123456789, 085123456789
        variations.append(f"'{clean_phone}'")  # Already added
        variations.append(f"'+{clean_phone}'")
        with_zero = '0' + clean_phone[2:]  # 62 -> 0
        variations.append(f"'{with_zero}'")
    elif clean_phone.startswith('0'):
        # 085123456789 -> +6285123456789, 6285123456789
        variations.append(f"'{clean_phone}'")  # Already added
        with_62 = '62' + clean_phone[1:]  # 0 -> 62
        variations.append(f"'{with_62}'")
        variations.append(f"'+{with_62}'")

    # Remove duplicates while preserving order
    seen = set()
    unique_variations = []
    for v in variations:
        if v not in seen:
            seen.add(v)
            unique_variations.append(v)

    logger.info(f"Phone number variations: {unique_variations}")

    # Build OR query
    phone_conditions = " OR ".join([f"phone_number = {v}" for v in unique_variations])
    sql_query = f"""
        SELECT account_type, account_expired_date
        FROM users
        WHERE ({phone_conditions})
        AND deleted_at IS NULL
        LIMIT 1
    """

    logger.info(f"VPS Query: {sql_query}")

    result = await query_vps_db(sql_query)

    if not result:
        logger.warning(f"VPS DB returned invalid result for phone_number: {phone_number}")
        return None

    # VPS DB API returns data in "rows" key
    users = result.get("rows", [])

    if not users or len(users) == 0:
        logger.info(f"No user found in VPS DB for phone_number: {phone_number}")
        return None

    account_type = users[0].get("account_type")
    account_expired_date = users[0].get("account_expired_date")
    logger.info(f"Found account_type in VPS DB: {account_type}, expired_date: {account_expired_date}")

    # Map 'premium' to 'plus'
    if account_type == 'premium':
        logger.info(f"Mapping 'premium' to 'plus'")
        account_type = 'plus'

    return {
        'account_type': account_type,
        'account_expired_date': account_expired_date
    }


async def get_device_type_from_vps(phone_number: str, device_id: Optional[int] = None) -> Optional[str]:
    """
    Get user's device type from VPS database by phone number.

    The device type is found by:
    1. Finding the user by phone_number
    2. Getting their device (first device if device_id not specified, or specific device by id)
    3. Looking up the device type's protocol or name

    Args:
        phone_number: Customer's phone number (can be in various formats)
        device_id: Optional specific device ID to look up. If None, returns first device.

    Returns:
        Device type string (from protocol or name column) or None if not found
    """
    logger.info(f"get_device_type_from_vps called - phone_number: {phone_number}, device_id: {device_id}")

    if not phone_number:
        logger.warning("Empty phone_number provided")
        return None

    # Generate phone number variations for matching
    variations = []

    # Original format
    clean_phone = phone_number.strip()
    variations.append(f"'{clean_phone}'")

    # Generate variations based on the format
    if clean_phone.startswith('+'):
        # +6285123456789 -> 6285123456789, 085123456789
        without_plus = clean_phone[1:]  # Remove +
        variations.append(f"'{without_plus}'")
        if without_plus.startswith('62'):
            with_zero = '0' + without_plus[2:]  # 62 -> 0
            variations.append(f"'{with_zero}'")
    elif clean_phone.startswith('62'):
        # 6285123456789 -> +6285123456789, 085123456789
        variations.append(f"'{clean_phone}'")  # Already added
        variations.append(f"'+{clean_phone}'")
        with_zero = '0' + clean_phone[2:]  # 62 -> 0
        variations.append(f"'{with_zero}'")
    elif clean_phone.startswith('0'):
        # 085123456789 -> +6285123456789, 6285123456789
        variations.append(f"'{clean_phone}'")  # Already added
        with_62 = '62' + clean_phone[1:]  # 0 -> 62
        variations.append(f"'{with_62}'")
        variations.append(f"'+{with_62}'")

    # Remove duplicates while preserving order
    seen = set()
    unique_variations = []
    for v in variations:
        if v not in seen:
            seen.add(v)
            unique_variations.append(v)

    logger.info(f"Phone number variations: {unique_variations}")

    # Step 1: Find user by phone number
    phone_conditions = " OR ".join([f"phone_number = {v}" for v in unique_variations])
    user_query = f"""
        SELECT id
        FROM users
        WHERE ({phone_conditions})
        AND deleted_at IS NULL
        LIMIT 1
    """

    logger.info(f"VPS User Query: {user_query}")

    user_result = await query_vps_db(user_query)

    if not user_result:
        logger.warning(f"VPS DB returned invalid result for phone_number: {phone_number}")
        return None

    users = user_result.get("rows", [])

    if not users or len(users) == 0:
        logger.info(f"No user found in VPS DB for phone_number: {phone_number}")
        return None

    user_id = users[0].get("id")
    logger.info(f"Found user in VPS DB: user_id = {user_id}")

    # Step 2: Get user's device (first device or specific device by id)
    if device_id:
        # Query for specific device by id
        device_query = f"""
            SELECT device_type_id
            FROM devices
            WHERE user_id = {user_id}
            AND id = {device_id}
            AND deleted_at IS NULL
            LIMIT 1
        """
        logger.info(f"VPS Device Query (by id {device_id}): {device_query}")
    else:
        # Query for first device (original behavior)
        device_query = f"""
            SELECT device_type_id
            FROM devices
            WHERE user_id = {user_id}
            AND deleted_at IS NULL
            LIMIT 1
        """
        logger.info(f"VPS Device Query (first device): {device_query}")

    device_result = await query_vps_db(device_query)

    if not device_result:
        logger.warning(f"VPS DB returned invalid result for user_id: {user_id}")
        return None

    devices = device_result.get("rows", [])

    if not devices or len(devices) == 0:
        logger.info(f"No devices found in VPS DB for user_id: {user_id}")
        return None

    device_type_id = devices[0].get("device_type_id")

    if not device_type_id:
        logger.warning(f"Device found but device_type_id is NULL for user_id: {user_id}")
        return None

    logger.info(f"Found device_type_id: {device_type_id}")

    # Step 3: Get device type protocol/name
    device_type_query = f"""
        SELECT protocol, name
        FROM device_types
        WHERE id = {device_type_id}
        LIMIT 1
    """

    logger.info(f"VPS Device Type Query: {device_type_query}")

    device_type_result = await query_vps_db(device_type_query)

    if not device_type_result:
        logger.warning(f"VPS DB returned invalid result for device_type_id: {device_type_id}")
        return None

    device_types = device_type_result.get("rows", [])

    if not device_types or len(device_types) == 0:
        logger.info(f"No device_type found in VPS DB for id: {device_type_id}")
        return None

    # Check protocol first, then name
    device_type = device_types[0].get("protocol") or device_types[0].get("name")

    if not device_type:
        logger.warning(f"Device type found but both protocol and name are NULL for device_type_id: {device_type_id}")
        return None

    logger.info(f"Found device type: {device_type}")
    return device_type


async def get_customer_devices_from_vps(phone_number: str) -> List[dict]:
    """
    Get all devices for a customer from VPS database by phone number.

    Args:
        phone_number: Customer's phone number (can be in various formats)

    Returns:
        List of device dicts with device_id, device_name, device_type (protocol/name), device_type_id, or empty list if not found
    """
    logger.info(f"get_customer_devices_from_vps called - phone_number: {phone_number}")

    if not phone_number:
        logger.warning("Empty phone_number provided")
        return []

    # Generate phone number variations for matching
    variations = []

    # Original format
    clean_phone = phone_number.strip()
    variations.append(f"'{clean_phone}'")

    # Generate variations based on the format
    if clean_phone.startswith('+'):
        # +6285123456789 -> 6285123456789, 085123456789
        without_plus = clean_phone[1:]  # Remove +
        variations.append(f"'{without_plus}'")
        if without_plus.startswith('62'):
            with_zero = '0' + without_plus[2:]  # 62 -> 0
            variations.append(f"'{with_zero}'")
    elif clean_phone.startswith('62'):
        # 6285123456789 -> +6285123456789, 085123456789
        variations.append(f"'{clean_phone}'")  # Already added
        variations.append(f"'+{clean_phone}'")
        with_zero = '0' + clean_phone[2:]  # 62 -> 0
        variations.append(f"'{with_zero}'")
    elif clean_phone.startswith('0'):
        # 085123456789 -> +6285123456789, 6285123456789
        variations.append(f"'{clean_phone}'")  # Already added
        with_62 = '62' + clean_phone[1:]  # 0 -> 62
        variations.append(f"'{with_62}'")
        variations.append(f"'+{with_62}'")

    # Remove duplicates while preserving order
    seen = set()
    unique_variations = []
    for v in variations:
        if v not in seen:
            seen.add(v)
            unique_variations.append(v)

    logger.info(f"Phone number variations: {unique_variations}")

    # Step 1: Find user by phone number
    phone_conditions = " OR ".join([f"phone_number = {v}" for v in unique_variations])
    user_query = f"""
        SELECT id
        FROM users
        WHERE ({phone_conditions})
        AND deleted_at IS NULL
        LIMIT 1
    """

    logger.info(f"VPS User Query: {user_query}")

    user_result = await query_vps_db(user_query)

    if not user_result:
        logger.warning(f"VPS DB returned invalid result for phone_number: {phone_number}")
        return []

    users = user_result.get("rows", [])

    if not users or len(users) == 0:
        logger.info(f"No user found in VPS DB for phone_number: {phone_number}")
        return []

    user_id = users[0].get("id")
    logger.info(f"Found user in VPS DB: user_id = {user_id}")

    # Step 2: Get all devices for the user
    device_query = f"""
        SELECT d.id as device_id, d.device_name, dt.protocol, dt.name, dt.id as device_type_id
        FROM devices d
        LEFT JOIN device_types dt ON d.device_type_id = dt.id
        WHERE d.user_id = {user_id}
        AND d.deleted_at IS NULL
        ORDER BY d.device_name ASC
    """

    logger.info(f"VPS All Devices Query: {device_query}")

    device_result = await query_vps_db(device_query)

    if not device_result:
        logger.warning(f"VPS DB returned invalid result for user_id: {user_id}")
        return []

    devices = device_result.get("rows", [])

    if not devices or len(devices) == 0:
        logger.info(f"No devices found in VPS DB for user_id: {user_id}")
        return []

    # Format the result
    formatted_devices = []
    for device in devices:
        device_type = device.get("protocol") or device.get("name")
        formatted_devices.append({
            'device_id': device.get('device_id'),
            'device_name': device.get('device_name'),
            'device_type': device_type,
            'device_type_id': device.get('device_type_id')
        })

    logger.info(f"Found {len(formatted_devices)} devices for user_id: {user_id}")
    return formatted_devices


async def get_vps_user_id_by_phone(phone_number: str) -> Optional[int]:
    """
    Get VPS user ID by phone number.

    This function queries the VPS database to find a user matching the given phone number
    and returns their user ID. It handles multiple phone number formats (with +62, 62, 0 prefix).

    Args:
        phone_number: Customer's phone number (can be in various formats)

    Returns:
        VPS user ID (int) if found, None if not found or on error
    """
    logger.info(f"get_vps_user_id_by_phone called - phone_number: {phone_number}")

    if not phone_number:
        logger.warning("Empty phone_number provided")
        return None

    # Use the existing phone utility to build SQL conditions
    phone_conditions = build_phone_number_sql_conditions(phone_number)

    # Query VPS DB for user ID
    sql_query = f"SELECT id FROM users WHERE ({phone_conditions}) AND deleted_at IS NULL LIMIT 1"

    logger.info(f"VPS Query for user ID: {sql_query}")

    result = await query_vps_db(sql_query)

    if not result:
        logger.warning(f"VPS DB returned invalid result for phone_number: {phone_number}")
        return None

    # VPS DB API returns data in "rows" key
    users = result.get("rows", [])

    if not users or len(users) == 0:
        logger.info(f"No user found in VPS DB for phone_number: {phone_number}")
        return None

    user_id = users[0].get("id")
    logger.info(f"Found VPS user_id: {user_id} for phone_number: {phone_number}")

    return user_id


async def get_vps_user_details(vps_user_id: int) -> Optional[dict]:
    """
    Get detailed user information from VPS database by user ID.

    This function fetches:
    - User's city (for domicile)
    - All device names for this user
    - Device count

    Args:
        vps_user_id: VPS user ID

    Returns:
        dict with:
            - city (str): User's city from VPS users table
            - device_names (list): List of device names from VPS devices table
            - unit_qty (int): Count of devices
            OR None if error
    """
    logger.info(f"get_vps_user_details called - vps_user_id: {vps_user_id}")

    if not vps_user_id:
        logger.warning("Empty vps_user_id provided")
        return None

    # Step 1: Get user's city from users table
    user_query = f"SELECT city FROM users WHERE id = {vps_user_id} AND deleted_at IS NULL LIMIT 1"

    logger.info(f"VPS Query for user city: {user_query}")

    user_result = await query_vps_db(user_query)

    if not user_result:
        logger.warning(f"VPS DB returned invalid result for user_id: {vps_user_id}")
        return None

    users = user_result.get("rows", [])

    if not users or len(users) == 0:
        logger.info(f"No user found in VPS DB for user_id: {vps_user_id}")
        return None

    city = users[0].get("city") or ""
    logger.info(f"Found city: '{city}' for user_id: {vps_user_id}")

    # Step 2: Get all device names for this user
    device_query = f"""
        SELECT device_name
        FROM devices
        WHERE user_id = {vps_user_id}
        AND deleted_at IS NULL
        ORDER BY device_name ASC
    """

    logger.info(f"VPS Query for devices: {device_query}")

    device_result = await query_vps_db(device_query)

    if not device_result:
        logger.warning(f"VPS DB returned invalid result for devices query")
        return {
            'city': city,
            'device_names': [],
            'unit_qty': 0
        }

    devices = device_result.get("rows", [])

    # Extract device names
    device_names = [device.get("device_name") for device in devices if device.get("device_name")]
    unit_qty = len(device_names)

    logger.info(f"Found {unit_qty} devices for user_id: {vps_user_id}: {device_names}")

    return {
        'city': city,
        'device_names': device_names,
        'unit_qty': unit_qty
    }
