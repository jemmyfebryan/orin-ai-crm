"""
Admin endpoint Pydantic schemas.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional


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
