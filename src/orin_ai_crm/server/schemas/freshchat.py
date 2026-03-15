"""
Freshchat-specific Pydantic schemas.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


class FreshchatAgentRequest(BaseModel):
    """Freshchat agent endpoint request schema."""
    phone_number: Optional[str] = Field(None, description="Nomor WhatsApp user (format: 628xxx)")
    lid_number: Optional[str] = Field(None, description="WhatsApp LID number untuk migrasi")
    message: str = Field(..., description="Pesan dari user")
    contact_name: Optional[str] = Field(None, description="Nama kontak dari WhatsApp")
    is_new_chat: bool = Field(False, description="Apakah ada pesan user pertama kali di WhatsApp")
    conversation_id: str = Field(..., description="Freshchat conversation ID")
    user_id: str = Field(..., description="Freshchat user ID")
    async_mode: bool = Field(True, description="Run asynchronously (background) or synchronously (wait for completion)")

    @field_validator('contact_name')
    @classmethod
    def validate_at_least_one_identifier(cls, v: Optional[str], info) -> Optional[str]:
        """Pastikan minimal salah satu identifier (phone_number atau lid_number) ada"""
        phone = info.data.get('phone_number')
        lid = info.data.get('lid_number')
        if not phone and not lid:
            raise ValueError('Minimal salah satu dari phone_number atau lid_number harus diisi')
        return v


class FreshchatAgentResponse(BaseModel):
    """Freshchat agent endpoint response schema."""
    status: str
    message: str


class FreshchatWebhookResponse(BaseModel):
    """Freshchat webhook endpoint response schema."""
    status: str


class FreshchatMessagePayload(BaseModel):
    """Freshchat message payload schema."""
    actor_type: str = "agent"
    actor_id: str
    message_type: str = "normal"
    message_parts: List[dict]
