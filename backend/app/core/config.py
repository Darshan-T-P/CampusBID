from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./campusbid.db"
    secret_key: str = "dev-secret-change-me-please-use-32-bytes-min"
    access_token_expire_minutes: int = 60 * 24
    # How often the background closer looks for expired auctions; 0 turns it off.
    closer_interval_seconds: float = 1.0
    # Where uploaded listing photos are stored (served at /media).
    media_dir: str = "media"
    # Comma-separated campus domains, e.g. "college.edu,mail.college.edu". Subdomains match too.
    # Required unless dev_mode is on (the app refuses to start without it).
    allowed_email_domains: str = ""
    # Demo/dev switch: relaxes the domain requirement and prints verification codes to the log.
    dev_mode: bool = False
    # Skip the email step and mark new accounts verified (demos, local testing).
    auto_verify: bool = False
    verification_code_ttl_minutes: int = 10
    verification_max_attempts: int = 5
    verification_resend_cooldown_seconds: int = 60
    rate_limit_enabled: bool = True


    @property
    def email_domains(self) -> list[str]:
        return [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]


settings = Settings()
