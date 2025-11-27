"""Configuration management for Sensei using pydantic-settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
	"""Application settings loaded from environment variables."""

	model_config = SettingsConfigDict(
		env_file=".env",
		env_file_encoding="utf-8",
		case_sensitive=False,
		extra="ignore",
	)

	# LLM API Keys
	anthropic_api_key: str = Field(
		default="",
		description="Anthropic API key for Claude",
	)
	grok_api_key: str = Field(
		default="",
		description="xAI Grok API key",
	)
	google_api_key: str = Field(
		default="",
		description="Google API key for Google Gemini",
	)

	# Documentation Services
	context7_api_key: str = Field(
		default="",
		description="Context7 API key for MCP server",
	)
	tavily_api_key: str = Field(
		default="",
		description="Tavily API key for MCP server",
	)

	# Database
	database_url: str = Field(
		default="sqlite+aiosqlite:///./sensei.db",
		description="Database connection URL",
	)

	# Server settings
	sensei_host: str = Field(
		default="http://localhost:8000",
		description="Base URL where Sensei server is running",
	)

	# Cache settings
	cache_ttl_days: int = Field(
		default=30,
		description="Soft TTL for cached queries in days",
	)
	max_recursion_depth: int = Field(
		default=2,
		description="Maximum recursion depth for sub-sensei spawning",
	)


# Global settings instance
settings = Settings()
