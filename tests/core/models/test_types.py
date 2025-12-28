import pytest
from pydantic import ValidationError
from src.orin_ai_crm.core.models.types import CustomerProfile

def test_customer_profile_default_values():
    """Verify that a CustomerProfile initializes with correct defaults."""
    profile = CustomerProfile()
    
    assert profile.phone_number == ""
    assert profile.lid_number == ""
    assert profile.source == ""
    assert profile.journey == "profiling"
    assert profile.category == "unknown"

def test_customer_profile_custom_values():
    """Verify that custom values are correctly assigned."""
    profile = CustomerProfile(
        phone_number="+628123456789",
        journey="educating",
        category="business"
    )
    
    assert profile.phone_number == "+628123456789"
    assert profile.journey == "educating"
    assert profile.category == "business"

def test_customer_profile_invalid_journey():
    """Verify that Pydantic raises an error for an invalid journey value."""
    with pytest.raises(ValidationError) as exc_info:
        CustomerProfile(journey="invalid_stage")
    
    # Check if the error message mentions the Literal options
    assert "Input should be 'profiling', 'educating' or 'handover'" in str(exc_info.value)

def test_customer_profile_invalid_category():
    """Verify that Pydantic raises an error for an invalid category value."""
    with pytest.raises(ValidationError) as exc_info:
        CustomerProfile(category="vip_client")
    
    assert "Input should be 'unknwon', 'personal', 'business' or 'other'" in str(exc_info.value)

def test_customer_profile_serialization():
    """Verify that the model can be converted to a dictionary and back."""
    data = {
        "phone_number": "+62811111",
        "lid_number": "LID-123",
        "source": "instagram",
        "journey": "handover",
        "category": "personal"
    }
    
    profile = CustomerProfile(**data)
    assert profile.model_dump() == data

def test_category_typo_check():
    """
    Note: Your source code has a typo 'unknwon'. 
    This test ensures we catch that specific string until it is fixed.
    """
    profile = CustomerProfile(category="unknwon")
    assert profile.category == "unknwon"