"""Settings configuration for ProjectGen using Pydantic and environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class LLMSettings(BaseSettings):
    """LLM configuration settings."""
    
    # model: str = Field(default="gpt-4o", description="OpenAI model to use for code generation")
    model: str = Field(default="gpt-5-nano", description="OpenAI model to use for code generation")
    model_spec_agent: str = Field(default="gpt-4o-mini", description="OpenAI model specifically for spec agent")
    # temperature: float = Field(default=1.0, description="Temperature for LLM responses")
    temperature: float = Field(default=1.0, description="Temperature for LLM responses")
    max_tokens: Optional[int] = Field(default=None, description="Maximum tokens for LLM responses")
    timeout: int = Field(default=60, description="Timeout for LLM requests in seconds")
    fix_placeholders: bool = Field(default=False, description="Flag for fixing placeholders after first step of the code file generation")

    class Config:
        env_prefix = "LLM_"
        env_file = ".env"
        env_file_encoding = "utf-8"


class ProjectGenSettings(BaseSettings):
    """Main ProjectGen settings."""
    
    # LLM settings
    llm: LLMSettings = Field(default_factory=LLMSettings)
    
    # General settings
    use_llm: bool = Field(default=True, description="Whether to use LLM for code generation")
    debug: bool = Field(default=False, description="Enable debug logging")
    cache_specs: bool = Field(default=True, description="Cache generated specifications")
    
    class Config:
        env_prefix = "PROJECTGEN_"
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = ProjectGenSettings()
