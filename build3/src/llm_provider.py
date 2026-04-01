"""Multi-LLM provider support for Build 3."""
import os
from typing import Optional

from langchain_core.language_models import BaseChatModel


def get_llm_provider() -> str:
    """Get LLM provider from environment."""
    return os.getenv("LLM_PROVIDER", "openai").lower()


def create_llm(
    model: Optional[str] = None,
    temperature: float = 0.2,
    streaming: bool = False,
) -> BaseChatModel:
    """Create LLM instance based on provider setting.
    
    Supports: openai, anthropic, kimi (openai-compatible)
    
    Args:
        model: Model name (provider-specific default if None)
        temperature: Sampling temperature
        streaming: Whether to stream output
        
    Returns:
        Configured LLM instance
    """
    provider = get_llm_provider()
    
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or "gpt-4o-mini",
            temperature=temperature,
            streaming=streaming,
        )
    
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model or "claude-3-sonnet-20240229",
            temperature=temperature,
            streaming=streaming,
        )
    
    elif provider == "kimi":
        from langchain_openai import ChatOpenAI
        # Kimi uses OpenAI-compatible API
        return ChatOpenAI(
            model=model or "kimi-latest",
            temperature=temperature,
            streaming=streaming,
            base_url="https://api.moonshot.cn/v1",
            api_key=os.getenv("KIMI_API_KEY"),
        )
    
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. "
                        "Set LLM_PROVIDER to 'openai', 'anthropic', or 'kimi'")


def get_provider_name() -> str:
    """Get human-readable provider name."""
    return get_llm_provider().upper()
