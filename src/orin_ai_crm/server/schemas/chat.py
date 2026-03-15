"""
Chat-related Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


class ChatRequest(BaseModel):
    """Legacy chat endpoint request schema."""
    phone_number: Optional[str] = Field(None, description="Nomor WhatsApp user (format: 628xxx)")
    lid_number: Optional[str] = Field(None, description="WhatsApp LID number untuk migrasi")
    message: str = Field(..., description="Pesan dari user")
    contact_name: Optional[str] = Field(None, description="Nama kontak dari WhatsApp")

    is_new_chat: bool = Field(False, description="Apakah ada pesan user pertama kali di WhatsApp")

    @field_validator('contact_name')
    @classmethod
    def validate_at_least_one_identifier(cls, v: Optional[str], info) -> Optional[str]:
        """Pastikan minimal salah satu identifier (phone_number atau lid_number) ada"""
        phone = info.data.get('phone_number')
        lid = info.data.get('lid_number')
        if not phone and not lid:
            raise ValueError('Minimal salah satu dari phone_number atau lid_number harus diisi')
        return v


class ChatResponse(BaseModel):
    """Legacy chat endpoint response schema."""
    customer_id: Optional[int]
    phone_number: Optional[str]
    lid_number: Optional[str]
    reply: str
    route: str
    step: str


class ChatAgentRequest(BaseModel):
    """New agentic endpoint request schema (30+ granular tools)."""
    phone_number: Optional[str] = Field(None, description="Nomor WhatsApp user (format: 628xxx)")
    lid_number: Optional[str] = Field(None, description="WhatsApp LID number untuk migrasi")
    message: str = Field(..., description="Pesan dari user")
    contact_name: Optional[str] = Field(None, description="Nama kontak dari WhatsApp")

    is_new_chat: bool = Field(False, description="Apakah ada pesan user pertama kali di WhatsApp")

    @field_validator('contact_name')
    @classmethod
    def validate_at_least_one_identifier(cls, v: Optional[str], info) -> Optional[str]:
        """Pastikan minimal salah satu identifier (phone_number atau lid_number) ada"""
        phone = info.data.get('phone_number')
        lid = info.data.get('lid_number')
        if not phone and not lid:
            raise ValueError('Minimal salah satu dari phone_number atau lid_number harus diisi')
        return v


class ChatAgentResponse(BaseModel):
    """New agentic endpoint response schema (30+ granular tools)."""
    customer_id: Optional[int]
    phone_number: Optional[str]
    lid_number: Optional[str]
    reply: str  # Kept for backward compatibility - will be first message from final_messages
    replies: list[str]  # New field: multi-bubble messages from final_messages
    tool_calls: Optional[list[str]] = None
    messages_count: int
