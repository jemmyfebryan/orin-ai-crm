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
        self.live_agent_user_id = os.getenv("LIVE_AGENT_USER_ID", "")

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

        # Allowlist for beta testing - parse comma-separated from env
        # If empty, allow all numbers (no filter)
        allowed_numbers_env = os.getenv("ALLOWED_NUMBERS", "")
        self.allowed_numbers = (
            [num.strip() for num in allowed_numbers_env.split(",") if num.strip()]
            if allowed_numbers_env else []
        )

        # Assets URL for product images and public files
        self.assets_url = os.getenv("ASSETS_URL", "")


# Global settings instance
settings = Settings()
