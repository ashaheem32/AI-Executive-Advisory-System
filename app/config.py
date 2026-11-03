from dataclasses import dataclass, field
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.getenv("DATABASE_PATH", str(ROOT / "data/northstar.db"))))
    demo: bool = field(default_factory=lambda: os.getenv("APP_DEMO", "1") == "1")
    secure_cookie: bool = field(default_factory=lambda: os.getenv("COOKIE_SECURE", "0") == "1")
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    allowed_hosts: list = field(default_factory=lambda: os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(","))
    max_upload: int = 5 * 1024 * 1024
    max_text: int = 250_000
    session_seconds: int = 8 * 60 * 60

    def validate(self):
        if not self.demo:
            if not self.secure_cookie:
                raise RuntimeError("Non-demo mode requires COOKIE_SECURE=1 and HTTPS.")
            for key in ("ADMIN_PASSWORD", "USER_PASSWORD"):
                value = os.getenv(key, "")
                if len(value) < 14 or "Demo!" in value:
                    raise RuntimeError(f"Set a unique {key} of at least 14 characters.")
