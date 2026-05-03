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

    # Namespace where kaniko Jobs are created (default: same ns as the service)
    builder_namespace: str = "agent-system"

    # K8s secret name containing .dockerconfigjson for registry push auth.
    # Leave unset when pushing to an unauthenticated local registry.
    registry_secret: str | None = None

    # Set true when the destination registry is HTTP-only (e.g. in-cluster registry:2).
    # Passes --insecure to kaniko so it skips TLS for the push.
    registry_insecure: bool = False

    # How long to wait for a kaniko Job to complete before marking the build failed
    build_timeout: float = 600.0
    build_poll_interval: float = 5.0


settings = Settings()
