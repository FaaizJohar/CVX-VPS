"""Agent configuration and state (credential) storage.

The credential file is written with mode 0600 and owned by root. It never
appears in logs or API responses.
"""

import os
import stat
from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_DIR = Path("/etc/cvx-agent")
CONFIG_FILE = CONFIG_DIR / "config.yaml"
CREDENTIAL_FILE = CONFIG_DIR / "credential"

DEFAULT_PORT = 9700


@dataclass(slots=True)
class AgentConfig:
    control_plane: str
    credential: str | None = None
    port: int = DEFAULT_PORT

    @classmethod
    def load(cls) -> "AgentConfig | None":
        if not CONFIG_FILE.exists():
            return None
        raw = yaml.safe_load(CONFIG_FILE.read_text()) or {}
        cfg = cls(
            control_plane=raw.get("control_plane", ""),
            port=int(raw.get("port", DEFAULT_PORT)),
        )
        if CREDENTIAL_FILE.exists():
            cfg.credential = CREDENTIAL_FILE.read_text().strip()
        return cfg

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            yaml.safe_dump(
                {"control_plane": self.control_plane, "port": self.port},
                default_flow_style=False,
            )
        )
        if self.credential:
            CREDENTIAL_FILE.write_text(self.credential)
            os.chmod(CREDENTIAL_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 0600
