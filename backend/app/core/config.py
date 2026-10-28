from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./campusbid.db"
    secret_key: str = "dev-secret-change-me-please-use-32-bytes-min"
    access_token_expire_minutes: int = 60 * 24
    # Empty = any email may register; e.g. "college.edu" restricts to that domain.
    allowed_email_domain: str = ""


settings = Settings()
