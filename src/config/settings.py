"""Application settings using Pydantic BaseSettings.

Configuration loading strategy:
1. Read ENV from .env or environment variable (default: develop)
2. Load settings from .env.{ENV} file (.env.develop or .env.product)
3. Allow .env to override any values for local customization
4. Environment variables always take highest precedence

This approach keeps sensitive/environment-specific config separate:
- .env.example: Template (committed to git)
- .env: Local selector + overrides (NOT committed)
- .env.develop: Development config (can be committed if no secrets)
- .env.product: Production config (can be committed if no secrets)
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_env_file() -> str:
    """Determine which environment file to load based on ENV variable.

    Priority:
    1. ENV environment variable
    2. ENV in .env file
    3. Default: develop

    Returns:
        Full path to the environment file
    """
    # First, try to load .env to get ENV selector
    root_dir = Path(__file__).parent.parent.parent
    dotenv_path = root_dir / ".env"

    if dotenv_path.exists():
        load_dotenv(dotenv_path, override=False)

    env = os.getenv("ENV", "develop")
    env_file_path = root_dir / f".env.{env}"

    # Verify the env file exists
    if not env_file_path.exists():
        raise FileNotFoundError(
            f"Environment file not found. Expected at: {env_file_path}"
        )

    return str(env_file_path)


class Settings(BaseSettings):
    """Application configuration from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(
            _get_env_file(),
            str(Path(__file__).parent.parent.parent / ".env"),
        ),  # Load env-specific first, then .env for overrides
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Environment ---
    env: Literal["develop", "product"] = "develop"

    # --- GCP Configuration ---
    gcp_project_id: str
    gcp_location: str = "asia-southeast1"

    # --- Vertex AI Search ---
    data_store_id: str
    search_engine_id: str  # Search App engine ID for retrieval
    data_store_location: str = "global"

    # --- Vertex AI Models ---
    # Override via env vars to switch models without code changes.
    # Current GA: gemini-2.5-flash, gemini-2.5-flash-lite, gemini-2.5-pro
    # Preview (3.x): gemini-3-flash-preview, gemini-3.1-pro-preview,
    #                 gemini-3.1-flash-lite-preview
    generation_model: str = "gemini-2.5-flash"
    generation_model_location: str | None = None  # Falls back to gcp_location
    review_model: str = "gemini-3.1-flash-lite-preview"
    review_model_location: str | None = None  # Falls back to gcp_location

    # --- Cloud Storage ---
    gcs_bucket: str

    # --- Firestore ---
    firestore_database: str

    # --- Cloud Tasks ---
    cloud_tasks_queue: str = "generation-queue"
    cloud_tasks_location: str = "asia-southeast1"
    cloud_tasks_invoker_service_account: str | None = None

    # --- Cloud Run ---
    cloud_run_base_url: str | None = None

    # --- Local Development ---
    local_async_mode: bool = False

    # --- Service Identity ---
    system_user_id: str = "__system__"

    # --- Logging ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Computed Properties ---
    @property
    def data_store_path(self) -> str:
        """Full resource path for Vertex AI Search data store."""
        return (
            f"projects/{self.gcp_project_id}/"
            f"locations/{self.data_store_location}/"
            f"collections/default_collection/"
            f"dataStores/{self.data_store_id}"
        )

    @property
    def search_engine_path(self) -> str:
        """Full resource path for Vertex AI Search engine."""
        return (
            f"projects/{self.gcp_project_id}/"
            f"locations/{self.data_store_location}/"
            f"collections/default_collection/"
            f"engines/{self.search_engine_id}"
        )

    @property
    def cloud_tasks_queue_path(self) -> str:
        """Full resource path for Cloud Tasks queue."""
        return (
            f"projects/{self.gcp_project_id}/"
            f"locations/{self.cloud_tasks_location}/"
            f"queues/{self.cloud_tasks_queue}"
        )

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.env == "product"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Using lru_cache ensures settings are loaded once and reused.
    Call clear_settings_cache() if you need to reload.
    """
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache to force reload.

    Useful for testing or when environment changes.
    """
    get_settings.cache_clear()
