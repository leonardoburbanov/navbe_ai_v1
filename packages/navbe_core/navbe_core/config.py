"""Navbe profile-home configuration.

Data and control plane live under ~/.navbe (or %USERPROFILE%\\.navbe on Windows).
Override with NAVBE_HOME.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

NAVBE_HOME = Path(os.environ.get("NAVBE_HOME", Path.home() / ".navbe"))
NAVBE_HOME.mkdir(parents=True, exist_ok=True)

CONTROL_DB = NAVBE_HOME / "control.db"
DATA_DIR = NAVBE_HOME / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{CONTROL_DB}"


class Settings(BaseSettings):
    """Runtime settings for the daemon (host/port). Paths come from NAVBE_HOME."""

    HOST: str = "127.0.0.1"
    PORT: int = 7700
    ENVIRONMENT: str = "development"
    # Control UI origin for MCP live_url deep links (env: NAVBE_UI_URL).
    UI_URL: str = "http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_prefix="NAVBE_", env_file=".env", extra="ignore")


settings = Settings()


class ProfileInfo(BaseModel):
    """Public view of the active profile home."""

    home: str = Field(description="Navbe profile directory")
    control_db: str
    data_dir: str


def profile_info() -> ProfileInfo:
    """Return the active profile paths."""
    return ProfileInfo(
        home=str(NAVBE_HOME),
        control_db=str(CONTROL_DB),
        data_dir=str(DATA_DIR),
    )
