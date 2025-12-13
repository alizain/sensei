"""Configuration management for Sensei using pydantic-settings."""

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import EnvSettingsSource

from sensei.paths import get_local_database_url


def export_settings_to_environ(settings: BaseSettings) -> None:
    """Export pydantic-settings values back to os.environ.

    This reverses what pydantic-settings does when reading from env vars,
    allowing libraries like PydanticAI (which use os.getenv() directly)
    to find these values.

    Uses pydantic-settings' own _extract_field_info method to compute
    the correct env var name, respecting env_prefix and aliases.
    """
    settings_cls = type(settings)
    source = EnvSettingsSource(settings_cls)

    for field_name, field_info in settings_cls.model_fields.items():
        value = getattr(settings, field_name)
        if not value:
            continue

        # Use pydantic-settings' own logic to get the env var name
        # Returns list of (field_key, env_name, value_is_complex)
        field_infos = source._extract_field_info(field_info, field_name)
        if not field_infos:
            continue

        # Get the first (preferred) env name
        _, env_name, _ = field_infos[0]

        # env_name is lowercased if case_sensitive=False, so uppercase it
        # to match the canonical env var convention
        env_name_canonical = env_name.upper()

        # Only export if not already in os.environ (don't override real env vars)
        if env_name_canonical not in os.environ:
            os.environ[env_name_canonical] = str(value)


class GeneralSettings(BaseSettings):
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

    # [Observability] Logfire
    logfire_token: str = Field(
        default="",
        description="Logfire write token for tracing",
    )
    logfire_service_name: str = Field(
        default="",
        description="Service name for Logfire tracing",
    )

    # [Observability] Langfuse
    langfuse_public_key: str = Field(default="", description="Langfuse public key for production tracing")
    langfuse_secret_key: str = Field(
        default="",
        description="Langfuse secret key for production tracing",
    )
    langfuse_base_url: str = Field(
        default="",
        description="Langfuse host URL",
    )


class SenseiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SENSEI_",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM model
    model: str = Field(default="", description="Which model & provider to use")

    # Database
    database_url: str = Field(
        default_factory=get_local_database_url,
        description="Database connection URL (defaults to local PostgreSQL via Unix socket)",
    )
    database_auto_migrate: bool = Field(
        default=True,
        description="Run database migrations on startup",
    )

    @property
    def is_external_database(self) -> bool:
        """Check if using an external (user-provided) database.

        Returns True if database_url differs from the local default.
        If external, sensei won't start PostgreSQL and won't run migrations
        (user is responsible for their own DB).
        """
        return self.database_url != get_local_database_url()

    # Server settings
    host: str = Field(
        default="",
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


general_settings = GeneralSettings()
sensei_settings = SenseiSettings()

# Export all settings to os.environ so libraries like PydanticAI
# (which use os.getenv() directly) can find them
export_settings_to_environ(general_settings)
export_settings_to_environ(sensei_settings)
