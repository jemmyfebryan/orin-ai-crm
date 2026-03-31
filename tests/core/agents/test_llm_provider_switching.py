"""
Test dynamic LLM provider switching between OpenAI and Gemini.
"""

import os
from unittest.mock import patch

from src.orin_ai_crm.core.agents.config import get_llm, LLMProvider, llm_config, LLMConfig


def test_llm_provider_enum():
    """Test LLMProvider enum values."""
    print("\n" + "="*80)
    print("TEST: LLMProvider Enum")
    print("="*80)

    assert LLMProvider.OPENAI == "openai"
    assert LLMProvider.GEMINI == "gemini"
    print("✓ LLMProvider enum has correct values")


def test_llm_config_default_provider():
    """Test default provider is OpenAI."""
    print("\n" + "="*80)
    print("TEST: Default LLM Provider")
    print("="*80)

    assert llm_config.PROVIDER == LLMProvider.OPENAI
    print(f"✓ Default provider is: {llm_config.PROVIDER}")


def test_llm_config_model_properties():
    """Test model name properties for OpenAI."""
    print("\n" + "="*80)
    print("TEST: Model Name Properties")
    print("="*80)

    print(f"Advanced model: {llm_config.ADVANCED_MODEL}")
    print(f"Medium model: {llm_config.MEDIUM_MODEL}")
    print(f"Basic model: {llm_config.BASIC_MODEL}")

    assert llm_config.ADVANCED_MODEL == "gpt-4o"
    assert llm_config.MEDIUM_MODEL == "gpt-4o-mini"
    assert llm_config.BASIC_MODEL == "gpt-4o-mini"
    print("✓ Model names are correct for OpenAI")


def test_get_llm_returns_openai_by_default():
    """Test get_llm returns ChatOpenAI by default."""
    print("\n" + "="*80)
    print("TEST: get_llm() Returns ChatOpenAI")
    print("="*80)

    # Mock the API key to avoid real API call
    with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
        llm = get_llm("advanced")

        from langchain_openai import ChatOpenAI
        assert isinstance(llm, ChatOpenAI)
        # Note: model_name is the correct attribute for ChatOpenAI
        assert llm.model_name == "gpt-4o"
        print(f"✓ get_llm('advanced') returns ChatOpenAI with model: {llm.model_name}")


def test_get_llm_explicit_openai_provider():
    """Test get_llm with explicit OpenAI provider."""
    print("\n" + "="*80)
    print("TEST: get_llm() with Explicit OpenAI Provider")
    print("="*80)

    with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
        llm = get_llm("medium", provider="openai")

        from langchain_openai import ChatOpenAI
        assert isinstance(llm, ChatOpenAI)
        assert llm.model_name == "gpt-4o-mini"
        print(f"✓ get_llm('medium', provider='openai') returns ChatOpenAI")


def test_get_llm_gemini_provider():
    """Test get_llm with Gemini provider."""
    print("\n" + "="*80)
    print("TEST: get_llm() with Gemini Provider")
    print("="*80)

    with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
        llm = get_llm("advanced", provider="gemini")

        from langchain_google_genai import ChatGoogleGenerativeAI
        assert isinstance(llm, ChatGoogleGenerativeAI)
        # Verify it's NOT OpenAI
        from langchain_openai import ChatOpenAI
        assert not isinstance(llm, ChatOpenAI)
        print(f"✓ get_llm('advanced', provider='gemini') returns ChatGoogleGenerativeAI")


def test_get_llm_gemini_medium_tier():
    """Test get_llm with Gemini medium tier."""
    print("\n" + "="*80)
    print("TEST: get_llm() Gemini Medium Tier")
    print("="*80)

    with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
        llm = get_llm("medium", provider=LLMProvider.GEMINI)

        from langchain_google_genai import ChatGoogleGenerativeAI
        assert isinstance(llm, ChatGoogleGenerativeAI)
        print(f"✓ get_llm('medium', provider=LLMProvider.GEMINI) returns ChatGoogleGenerativeAI")


def test_llm_config_with_gemini_provider():
    """Test LLMConfig with Gemini provider via env var."""
    print("\n" + "="*80)
    print("TEST: LLMConfig with Gemini Provider (via env)")
    print("="*80)

    # Create a new config instance with Gemini provider
    class TestLLMConfig(LLMConfig):
        PROVIDER = LLMProvider.GEMINI

    test_config = TestLLMConfig()

    print(f"Provider: {test_config.PROVIDER}")
    print(f"Advanced model: {test_config.ADVANCED_MODEL}")
    print(f"Medium model: {test_config.MEDIUM_MODEL}")
    print(f"Basic model: {test_config.BASIC_MODEL}")

    assert test_config.PROVIDER == LLMProvider.GEMINI
    assert test_config.ADVANCED_MODEL == "gemini-2.5-pro-preview-04-17"
    assert test_config.MEDIUM_MODEL == "gemini-2.0-flash-exp"
    assert test_config.BASIC_MODEL == "gemini-2.0-flash-exp"
    print("✓ Model names are correct for Gemini provider")


def test_get_llm_tier_fallback():
    """Test get_llm falls back to medium for unknown tier."""
    print("\n" + "="*80)
    print("TEST: get_llm() Tier Fallback")
    print("="*80)

    with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
        llm = get_llm("unknown_tier")

        from langchain_openai import ChatOpenAI
        assert isinstance(llm, ChatOpenAI)
        assert llm.model_name == "gpt-4o-mini"  # Falls back to medium
        print(f"✓ get_llm('unknown_tier') falls back to medium model: {llm.model_name}")


def test_temperature_parameter():
    """Test temperature parameter is passed through."""
    print("\n" + "="*80)
    print("TEST: Temperature Parameter")
    print("="*80)

    with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
        llm = get_llm("advanced", temperature=0.7)

        from langchain_openai import ChatOpenAI
        assert isinstance(llm, ChatOpenAI)
        assert llm.temperature == 0.7
        print(f"✓ Temperature parameter passed correctly: {llm.temperature}")


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("LLM PROVIDER SWITCHING TESTS")
    print("="*80)

    test_llm_provider_enum()
    test_llm_config_default_provider()
    test_llm_config_model_properties()
    test_get_llm_returns_openai_by_default()
    test_get_llm_explicit_openai_provider()
    test_get_llm_gemini_provider()
    test_get_llm_gemini_medium_tier()
    test_llm_config_with_gemini_provider()
    test_get_llm_tier_fallback()
    test_temperature_parameter()

    print("\n" + "="*80)
    print("✓ ALL TESTS PASSED")
    print("="*80)
    print("\nSummary:")
    print("  ✓ OpenAI provider works correctly")
    print("  ✓ Gemini provider works correctly")
    print("  ✓ Provider override parameter works")
    print("  ✓ All tier selections work")
    print("  ✓ Temperature parameter passes through")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
