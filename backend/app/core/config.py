from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./campusbid.db"
    secret_key: str = "dev-secret-change-me-please-use-32-bytes-min"
    # Password hashing cost (scrypt). N=2**15, r=8, p=3 is the OWASP-recommended equivalent; tests lower it.
    password_scrypt_n: int = 2**15
    password_scrypt_p: int = 3
    # Browser origins allowed to call the API directly (comma-separated). The dev proxy needs none of this.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Requests larger than this are refused with 413 before being read (5 photos x 5 MB, plus form overhead).
    max_request_bytes: int = 30 * 1024 * 1024
    access_token_expire_minutes: int = 60 * 24
    # How often the background closer looks for expired auctions; 0 turns it off.
    closer_interval_seconds: float = 1.0
    # Where uploaded listing photos are stored (served at /media).
    media_dir: str = "media"
    # Comma-separated campus domains, e.g. "college.edu,mail.college.edu". Subdomains match too.
    # Required unless dev_mode is on (the app refuses to start without it).
    allowed_email_domains: str = ""
    # Every registering email must end with this (institutional addresses). Empty disables the check.
    required_email_suffix: str = ".edu"
    # Demo/dev switch: relaxes the domain requirement and prints verification codes to the log.
    dev_mode: bool = False
    # Skip the email step and mark new accounts verified (demos, local testing).
    auto_verify: bool = False
    verification_code_ttl_minutes: int = 10
    verification_max_attempts: int = 5
    verification_resend_cooldown_seconds: int = 60
    rate_limit_enabled: bool = True


    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def secret_key_is_weak(self) -> bool:
        """True for the built-in dev value, an example placeholder, or anything too short to be a real secret."""
        key = self.secret_key
        return len(key) < 32 or key.startswith("dev-secret") or "change-me" in key.lower()

    @property
    def email_domains(self) -> list[str]:
        return [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]


settings = Settings()
