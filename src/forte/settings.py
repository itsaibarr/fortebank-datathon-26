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
    model_revision: str = "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
    max_context_tokens: int = 8192
    reasoning_config: Path | dict | None = None
    frontend_root: Path | None = None

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
            model_name=os.environ.get("FORTE_MODEL_NAME", "forte-vlm"),
            model_revision=os.environ.get(
                "FORTE_MODEL_REVISION", "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
            ),
            max_context_tokens=int(os.environ.get("FORTE_MAX_CONTEXT_TOKENS", "8192")),
            reasoning_config=(
                Path(os.environ["FORTE_REASONING_CONFIG"])
                if os.environ.get("FORTE_REASONING_CONFIG")
                else None
            ),
            frontend_root=(
                Path(os.environ["FORTE_FRONTEND_ROOT"])
                if os.environ.get("FORTE_FRONTEND_ROOT")
                else None
            ),
        )
