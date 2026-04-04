"""
Phone number utilities for Indonesian phone numbers.

Indonesian phone number formats:
- "+6285123456789" (international format with +)
- "6285123456789" (country code without +)
- "085123456789" (local format with 0 prefix)

All these represent the same phone number and should be treated as equivalent.
"""

from typing import List


def normalize_indonesian_phone_number(phone_number: str) -> str:
    """
    Normalize Indonesian phone number to standard format (62 prefix).

    Handles different phone number formats:
    - "+62123123123" → "62123123123"
    - "62123123123" → "62123123123" (already normalized)
    - "0123123123" → "62123123123"

    Args:
        phone_number: Phone number in any format

    Returns:
        Normalized phone number with "62" prefix (no +, no leading 0)

    Examples:
        >>> normalize_indonesian_phone_number("+6285123456789")
        "6285123456789"
        >>> normalize_indonesian_phone_number("085123456789")
        "6285123456789"
        >>> normalize_indonesian_phone_number("6285123456789")
        "6285123456789"
    """
    if not phone_number:
        return phone_number

    # Remove all non-digit characters (spaces, dashes, parentheses, etc.)
    normalized = phone_number.strip()
    normalized = ''.join(c for c in normalized if c.isdigit())

    # If starts with "0", replace with "62" (Indonesian local format)
    if normalized.startswith('0'):
        normalized = '62' + normalized[1:]
    # If starts with "+62", remove the "+"
    elif normalized.startswith('62'):
        # Already in correct format
        pass
    # If doesn't start with 62 or 0, assume it's already in the desired format
    # or it's an international number without country code

    return normalized


def generate_phone_number_variations(phone_number: str) -> List[str]:
    """
    Generate all possible variations of an Indonesian phone number for SQL queries.

    This is useful for matching phone numbers in databases where the format
    might be inconsistent (some entries use +62, some use 62, some use 0).

    Args:
        phone_number: Phone number in any format

    Returns:
        List of phone number variations (as strings, properly quoted for SQL)

    Examples:
        >>> generate_phone_number_variations("085123456789")
        ["'085123456789'", "'6285123456789'", "'+6285123456789'"]
        >>> generate_phone_number_variations("6285123456789")
        ["'6285123456789'", "'085123456789'", "'+6285123456789'"]
    """
    if not phone_number:
        return []

    variations = []

    # Original format (cleaned)
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
        variations.append(f"'+{clean_phone}'")  # Add + prefix
        with_zero = '0' + clean_phone[2:]  # 62 -> 0
        variations.append(f"'{with_zero}'")
    elif clean_phone.startswith('0'):
        # 085123456789 -> +6285123456789, 6285123456789
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

    return unique_variations


def build_phone_number_sql_conditions(phone_number: str, column_name: str = "phone_number") -> str:
    """
    Build SQL OR conditions for matching phone numbers in various formats.

    This generates SQL like:
    phone_number = '085123456789' OR phone_number = '6285123456789' OR phone_number = '+6285123456789'

    Args:
        phone_number: Phone number in any format
        column_name: Name of the column to query (default: "phone_number")

    Returns:
        SQL conditions string for use in WHERE clause

    Examples:
        >>> build_phone_number_sql_conditions("085123456789")
        "phone_number = '085123456789' OR phone_number = '6285123456789' OR phone_number = '+6285123456789'"
    """
    variations = generate_phone_number_variations(phone_number)
    conditions = [f"{column_name} = {v}" for v in variations]
    return " OR ".join(conditions)
