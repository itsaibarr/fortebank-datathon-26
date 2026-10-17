import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    api_key: str
    private_root: Path
    model_url: str = "http://127.0.0.1:8001"
    model_name: str = "forte-vlm"
    job_timeout: float = 270
    upload_timeout: float = 30
    upload_max_bytes: int = 268435456
    max_admitted: int = 2

    def __post_init__(self):
        if len(self.api_key) < 16 or not self.api_key.isascii():
            raise ValueError("Set a separate service API key of at least 16 ASCII characters")
        self.private_root = self.private_root.resolve()

    @classmethod
    def from_env(cls):
        key = os.environ.get("FORTE_API_KEY", "")
        if not key and os.environ.get("FORTE_API_KEY_FILE"):
            key = Path(os.environ["FORTE_API_KEY_FILE"]).read_text().strip()
        return cls(
            key,
            Path(
                os.environ.get("FORTE_PRIVATE_ROOT", str(Path.home() / ".local/share/forte26/jobs"))
            ),
            os.environ.get("FORTE_MODEL_URL", "http://127.0.0.1:8001"),
        )
