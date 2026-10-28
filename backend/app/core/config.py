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
    # --- Email (verification codes, password reset) ---------------------------------------------------
    # "console": nothing is sent; in dev mode the code is printed to the server log.
    # "smtp": real email through any SMTP provider (Gmail, Brevo, Resend, Mailgun, ...).
    email_backend: str = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True  # upgrade a plain connection to TLS (port 587)
    smtp_ssl: bool = False  # TLS from the first byte (port 465); turn starttls off if you use this
    smtp_timeout: int = 15
    email_from: str = "Relay <no-reply@localhost>"
    password_reset_code_ttl_minutes: int = 15
    # Where the web app lives, for the links inside emails (e.g. https://relay.example.edu).
    public_url: str = "http://localhost:5173"
    # --- AI assistant (Groq, an OpenAI-compatible API). Empty key = the assistant is switched off. ------------
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"  # must support tool calling; list what your key can use at /openai/v1/models
    groq_base_url: str = "https://api.groq.com/openai/v1"
    assistant_timeout: int = 25
    # The most auctions one student can have open at once (a guard against floods and runaway scripts).
    max_open_listings: int = 20
    # Production: serve the built frontend from this server (the API moves under /api). Off in development.
    serve_frontend: bool = False
    frontend_dist: str = "../frontend/dist"
    # Demo/dev switch: relaxes the domain requirement and prints verification codes to the log.
    dev_mode: bool = False
    # Skip the email step and mark new accounts verified (demos, local testing).
    auto_verify: bool = False
    verification_code_ttl_minutes: int = 10
    verification_max_attempts: int = 5
    verification_resend_cooldown_seconds: int = 60
    rate_limit_enabled: bool = True


    @property
    def smtp_ready(self) -> bool:
        return self.email_backend == "smtp" and bool(self.smtp_host.strip()) and bool(self.email_from.strip())

    @property
    def assistant_ready(self) -> bool:
        return bool(self.groq_api_key.strip())

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
