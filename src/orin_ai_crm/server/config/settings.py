"""
Centralized configuration for the application.

This module loads and validates all environment variables.
"""
import os
from typing import List


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self):
        # Freshchat Configuration
        self.freshchat_api_token = os.getenv("FRESHCHAT_API_TOKEN", "")
        self.freshchat_url = os.getenv("FRESHCHAT_URL", "")
        self.freshchat_agent_bearer_token = os.getenv("FRESHCHAT_AGENT_BEARER_TOKEN", "")
        self.agent_id_bot = os.getenv("AGENT_ID_BOT", "")
        self.freshchat_webhook_token = os.getenv("FRESHCHAT_WEBHOOK_TOKEN", "")
        self.freshchat_api_version = os.getenv("FRESHCHAT_API_VERSION", "v2")

        # Freshchat Webhook Security - parse comma-separated to list
        webhook_ips = os.getenv("FRESHCHAT_WEBHOOK_ALLOWED_IPS", "")
        self.freshchat_webhook_allowed_ips = (
            [ip.strip() for ip in webhook_ips.split(",") if ip.strip()]
            if webhook_ips else []
        )

        channel_ids = os.getenv("FRESHCHAT_ALLOWED_CHANNEL_IDS", "")
        self.freshchat_allowed_channel_ids = (
            [cid.strip() for cid in channel_ids.split(",") if cid.strip()]
            if channel_ids else []
        )

        # Allowlist for beta testing
        self.allowed_numbers = [
            "+628123456789",
            "+6285850434383",
        ]


# Global settings instance
settings = Settings()
