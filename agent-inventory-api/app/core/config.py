from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "agent-inventory-api"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agent_inventory"

    k8s_namespace: str = "agent-system"
    k8s_in_cluster: bool = True

    outbox_poll_interval: float = 5.0
    outbox_max_retries: int = 5
    outbox_processing_timeout: float = 300.0


settings = Settings()
