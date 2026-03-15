"""
Health check and debug endpoints.
"""
from fastapi import APIRouter

from src.orin_ai_crm.server.config.settings import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """Endpoint untuk health check"""
    return {
        "status": "healthy",
        "service": "HANA AI WhatsApp Chatbot",
        "version": "2.1 - Agentic Architecture (Optimized)",
        "endpoints": {
            "chat": "/chat (Legacy - Intent Classification)",
            "chat-agent": "/chat-agent (Agentic with recursion_limit=50)",
            "freshchat-agent": "/freshchat-agent (Freshchat API with BackgroundTasks)",
            "freshchat-webhook": "/freshchat-webhook (Freshchat Webhook with anti-loop)",
            "reset-history": "/reset-history",
            "reset-products": "/reset-products",
            "health": "/health"
        },
        "agent_tools": {
            "total": 18,
            "active": 15,
            "categories": [
                "Customer Management (1)",
                "Profiling (3)",
                "Sales & Meeting (6)",
                "Product & E-commerce (5)",
                "Support & Complaints (3) - available but not assigned to specific agent"
            ],
            "note": "get_customer_profile is invoked directly in agent_node before LLM runs to prevent infinite loops"
        },
        "freshchat_config": {
            "configured": bool(settings.freshchat_api_token and settings.freshchat_url and settings.agent_id_bot),
            "agent_auth": bool(settings.freshchat_agent_bearer_token),
            "webhook_auth": bool(settings.freshchat_webhook_token),
            "allowed_numbers": len(settings.allowed_numbers)
        }
    }


@router.get("/debug-webhook-key")
async def debug_webhook_key():
    """
    Debug endpoint to check if the Freshchat public key and allowlist are configured correctly.
    Remove this endpoint in production!
    """
    return {
        "status": "ok",
        "message": "Configuration loaded",
        "webhook_auth": {
            "configured": bool(settings.freshchat_webhook_token),
            "key_preview": settings.freshchat_webhook_token[:100] if settings.freshchat_webhook_token else None,
            "key_length": len(settings.freshchat_webhook_token) if settings.freshchat_webhook_token else 0,
        },
        "webhook_ip_allowlist": {
            "enabled": bool(settings.freshchat_webhook_allowed_ips and any(settings.freshchat_webhook_allowed_ips)),
            "allowed_ips": settings.freshchat_webhook_allowed_ips,
            "description": "If enabled, only webhooks from these IPs will be accepted"
        },
        "freshchat_api": {
            "configured": bool(settings.freshchat_api_token and settings.freshchat_url),
            "url": settings.freshchat_url
        },
        "allowlist": {
            "allowed_numbers": settings.allowed_numbers,
            "count": len(settings.allowed_numbers),
            "mode": "Restricted (phone number filter)"
        },
        "channel_filter": {
            "allowed_channel_ids": settings.freshchat_allowed_channel_ids,
            "description": "This AI CRM only responds to configured Freshchat channels",
            "find_your_channel_id": "Freshchat Admin > Channels > WhatsApp > Settings"
        }
    }
