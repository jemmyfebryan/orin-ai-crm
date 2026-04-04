"""
Admin endpoint Pydantic schemas.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any


class ResetCustomerRequest(BaseModel):
    """Request schema for delete-customer endpoint."""
    phone_number: Optional[str] = Field(None, description="Nomor WhatsApp user")
    lid_number: Optional[str] = Field(None, description="WhatsApp LID number")

    @field_validator('lid_number')
    @classmethod
    def validate_at_least_one_identifier(cls, v: Optional[str], info) -> Optional[str]:
        """Pastikan minimal salah satu identifier (phone_number atau lid_number) ada"""
        phone = info.data.get('phone_number')
        lid = v
        if not phone and not lid:
            raise ValueError('Minimal salah satu dari phone_number atau lid_number harus diisi')
        return v


class ResetCustomerResponse(BaseModel):
    """Response schema for delete-customer endpoint."""
    success: bool
    message: str
    deleted_tables: dict[str, int]
    customer_id: Optional[int] = None


class ResetProductsResponse(BaseModel):
    """Response schema for reset-products endpoint."""
    success: bool
    message: str
    deleted: int
    created: int
    errors: list[str]


class ProductItem(BaseModel):
    """Single product item."""
    id: int
    name: str
    sku: str
    category: str
    subcategory: Optional[str] = None
    vehicle_type: Optional[str] = None
    description: Optional[str] = None
    features: Optional[Dict[str, Any]] = None
    price: Optional[str] = None
    installation_type: str
    can_shutdown_engine: bool = False
    is_realtime_tracking: bool = True
    ecommerce_links: Optional[Dict[str, str]] = None
    images: Optional[list[str]] = None
    specifications: Optional[Dict[str, Any]] = None
    compatibility: Optional[Dict[str, Any]] = None
    is_active: bool = True
    sort_order: int = 0


class GetProductsResponse(BaseModel):
    """Response schema for get-products endpoint."""
    success: bool
    products: list[ProductItem]
    count: int


class UpdateProductRequest(BaseModel):
    """Request schema for update-product endpoint."""
    name: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    vehicle_type: Optional[str] = None
    description: Optional[str] = None
    features: Optional[Dict[str, Any]] = None
    price: Optional[str] = None
    installation_type: Optional[str] = None
    can_shutdown_engine: Optional[bool] = None
    is_realtime_tracking: Optional[bool] = None
    ecommerce_links: Optional[Dict[str, str]] = None
    images: Optional[list[str]] = None
    specifications: Optional[Dict[str, Any]] = None
    compatibility: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class UpdateProductResponse(BaseModel):
    """Response schema for update-product endpoint."""
    success: bool
    message: str
    product_id: int


class PromptItem(BaseModel):
    """Single prompt item."""
    prompt_key: str
    prompt_name: str
    prompt_text: str
    description: Optional[str] = None
    prompt_type: str = "system"
    is_active: bool = True


class GetPromptsResponse(BaseModel):
    """Response schema for get-prompts endpoint."""
    success: bool
    prompts: list[PromptItem]
    count: int


class UpdatePromptRequest(BaseModel):
    """Request schema for update-prompt endpoint."""
    prompt_text: str


class UpdatePromptResponse(BaseModel):
    """Response schema for update-prompt endpoint."""
    success: bool
    message: str
    prompt_key: str


class ResetPromptsResponse(BaseModel):
    """Response schema for reset-prompts endpoint."""
    success: bool
    message: str
    deleted: int
    created: int
    errors: list[str]


# ============================================================================
# CHAT HISTORY ENDPOINT SCHEMAS
# ============================================================================

class ContactItem(BaseModel):
    """Single contact/customer item."""
    id: int
    phone_number: Optional[str] = None
    name: Optional[str] = None
    domicile: Optional[str] = None
    vehicle: Optional[str] = None  # Combined from vehicle_id and vehicle_alias
    unit_qty: Optional[int] = None
    human_takeover: bool = False  # Whether human takeover is enabled
    created_at: Optional[str] = None  # ISO format datetime
    last_message_time: Optional[str] = None  # ISO format datetime


class GetContactsResponse(BaseModel):
    """Response schema for get-contacts endpoint."""
    success: bool
    contacts: list[ContactItem]
    count: int


class ChatMessageItem(BaseModel):
    """Single chat message item."""
    role: str  # 'user' or 'assistant' (mapped from 'ai')
    content: str
    timestamp: str  # ISO format datetime


class GetChatHistoryResponse(BaseModel):
    """Response schema for get-chat-history endpoint."""
    success: bool
    customer_id: int
    messages: list[ChatMessageItem]
    count: int


class ToggleHumanTakeoverResponse(BaseModel):
    """Response schema for toggle-human-takeover endpoint."""
    success: bool
    message: str
    customer_id: int
    human_takeover: bool  # The new state after toggle
