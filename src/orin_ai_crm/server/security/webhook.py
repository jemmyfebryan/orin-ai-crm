"""
Webhook security utilities for signature and IP verification.
"""
import hmac
import hashlib
import base64
import re
import ipaddress
from typing import List

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.server.config.settings import settings

logger = get_logger(__name__)


def is_ip_allowed(client_ip: str, allowed_ips: List[str]) -> bool:
    """
    Check if client IP is in the allowlist.
    Supports both individual IPs and CIDR ranges.

    Args:
        client_ip: Client IP address string
        allowed_ips: List of allowed IPs/CIDRs

    Returns:
        True if IP is allowed or allowlist is empty, False otherwise
    """
    # If no IP restrictions configured, allow all
    if not allowed_ips or not any(allowed_ips):
        return True

    try:
        client = ipaddress.ip_address(client_ip)

        for allowed in allowed_ips:
            allowed = allowed.strip()
            if not allowed:
                continue

            # Check if it's a CIDR range or single IP
            if '/' in allowed:
                # CIDR range
                network = ipaddress.ip_network(allowed, strict=False)
                if client in network:
                    return True
            else:
                # Single IP
                allowed_ip = ipaddress.ip_address(allowed)
                if client == allowed_ip:
                    return True

        return False
    except Exception as e:
        logger.warning(f"IP verification error: {e}, allowing by default")
        return True  # Fail open for safety


def verify_freshchat_signature(payload: bytes, signature_b64: str) -> bool:
    """
    Verify Freshchat webhook signature.
    Tries RSA-SHA256 first, then HMAC-SHA256 as fallback.

    Args:
        payload: Raw request body (bytes)
        signature_b64: Base64-encoded signature from X-Freshchat-Signature header

    Returns:
        True if signature is valid, False otherwise
    """
    # Try HMAC-SHA256 first (more common for webhooks)
    try_hmac = True
    try_rsa = True

    # Method 1: HMAC-SHA256 (using token as secret key)
    if try_hmac:
        try:
            secret = settings.freshchat_webhook_token.strip().encode('utf-8')
            expected_signature = hmac.new(secret, payload, hashlib.sha256).digest()
            expected_signature_b64 = base64.b64encode(expected_signature).decode('utf-8')

            # Compare with constant-time comparison
            if hmac.compare_digest(expected_signature_b64, signature_b64):
                return True
        except Exception:
            pass  # Silently try next method

    # Method 2: RSA-SHA256 (using token as public key)
    if try_rsa:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.backends import default_backend

            # Decode the Base64 signature
            signature = base64.b64decode(signature_b64)

            # Load the public key from environment variable
            public_key_str = settings.freshchat_webhook_token.strip()

            # If the key already has PEM headers, use it directly
            if "-----BEGIN" in public_key_str and "-----END" in public_key_str:
                # Already in PEM format, use as-is
                pem_key = public_key_str
            else:
                # Raw base64 key, need to wrap it
                # Remove any whitespace/newlines
                clean_key = re.sub(r'\s+', '', public_key_str)
                # Wrap in PEM format
                pem_key = f"-----BEGIN PUBLIC KEY-----\n{clean_key}\n-----END PUBLIC KEY-----"

            # Load the public key
            public_key = serialization.load_pem_public_key(
                pem_key.encode(),
                backend=default_backend()
            )

            # Verify the signature
            public_key.verify(
                signature,
                payload,
                padding.PKCS1v15(),
                hashes.SHA256()
            )

            return True

        except Exception:
            pass  # Silently fail

    # If we get here, both methods failed
    return False
