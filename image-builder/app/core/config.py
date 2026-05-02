"""Service configuration via pydantic-settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "image-builder"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/image_builder"
    )

    # Kubernetes — general
    k8s_namespace: str = "agent-system"
    k8s_in_cluster: bool = True

    # Kaniko build executor
    kaniko_image: str = "gcr.io/kaniko-project/executor:latest"

    # Namespace where kaniko Jobs are created
    builder_namespace: str = "image-builder-system"


settings = Settings()
