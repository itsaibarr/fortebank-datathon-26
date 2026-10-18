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
    trusted_gateway_token: str | None = None
    v1_pipeline: str = "legacy"

    def __post_init__(self):
        if self.v1_pipeline not in {"legacy", "reasoning"}:
            raise ValueError("Select an explicit v1 pipeline: legacy or reasoning")
        if self.v1_pipeline == "reasoning" and self.reasoning_config is None:
            raise ValueError(
                "The reasoning v1 pipeline requires an explicit reasoning configuration"
            )
        if len(self.api_key) < 16 or not self.api_key.isascii():
            raise ValueError("Set a separate service API key of at least 16 ASCII characters")
        if self.trusted_gateway_token is not None and (
            len(self.trusted_gateway_token) < 32
            or len(self.trusted_gateway_token) > 256
            or not self.trusted_gateway_token.isascii()
            or not all(33 <= ord(char) <= 126 for char in self.trusted_gateway_token)
        ):
            raise ValueError("Trusted gateway mode requires a separate 32–256 character secret")
        if self.trusted_gateway_token == self.api_key:
            raise ValueError("The trusted gateway token must differ from the service API key")
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
            trusted_gateway_token=(
                Path(os.environ["FORTE_TRUSTED_GATEWAY_TOKEN_FILE"]).read_text().strip()
                if os.environ.get("FORTE_TRUSTED_GATEWAY_TOKEN_FILE")
                else None
            ),
            frontend_root=(
                Path(os.environ["FORTE_FRONTEND_ROOT"])
                if os.environ.get("FORTE_FRONTEND_ROOT")
                else None
            ),
            v1_pipeline=os.environ.get("FORTE_V1_PIPELINE", "legacy"),
        )
