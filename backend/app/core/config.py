from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ParkVektor Private DE"
    app_env: str = "development"
    app_public_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    database_url: str = "sqlite:///./parkvektor_local.db"

    storage_backend: str = "local"  # "local" | "s3"
    local_storage_dir: str = "./local_storage"
    s3_endpoint_url: str | None = None
    s3_region: str = "eu-central-1"
    s3_bucket: str = "parkvektor-evidence-de"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    payment_provider: str = "mock"  # "mock" | "stripe"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    admin_api_key: str = "dev-admin-key-change-in-prod"
    default_edge_hmac_secret: str = "dev-lane-secret-change-in-prod"
    auto_seed_demo_data: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
