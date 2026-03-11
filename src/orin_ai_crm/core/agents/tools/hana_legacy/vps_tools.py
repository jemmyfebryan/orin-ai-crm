"""
VPS Database Tools - Query external VPS database for vehicle data
"""

import os
from typing import Optional, List
from dotenv import load_dotenv
import httpx
from sqlalchemy import select

from src.orin_ai_crm.core.logger import get_logger

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
