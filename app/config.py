"""Configuration loading.

Non-secret, machine-specific settings live in config/config.yaml
(copied from config.example.yaml). Secrets (Supabase URL/key) live in
.env and are never written into config.yaml or source control.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

# When frozen into an .exe (PyInstaller), __file__ points inside the
# bundled/temp payload, not the distribution folder — resolve relative
# to the executable itself instead, so config/templates/data next to
# the .exe are found correctly.
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class PrinterConfig:
    name: str = ""
    copies: int = 1


@dataclass
class TemplateConfig:
    path: str = "templates/ticket_template.docx"
    number_padding: int = 3


@dataclass
class DatabaseConfig:
    path: str = "data/queue.db"


@dataclass
class SyncConfig:
    enabled: bool = True
    interval_seconds: int = 15
    batch_size: int = 25


@dataclass
class LoggingConfig:
    dir: str = "data/logs"
    level: str = "INFO"


@dataclass
class SupabaseConfig:
    url: str = ""
    key: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)


@dataclass
class AppConfig:
    printer: PrinterConfig = field(default_factory=PrinterConfig)
    template: TemplateConfig = field(default_factory=TemplateConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    supabase: SupabaseConfig = field(default_factory=SupabaseConfig)

    def resolve_path(self, relative: str) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else PROJECT_ROOT / p


def load_config(config_path: str | Path | None = None) -> AppConfig:
    load_dotenv(PROJECT_ROOT / ".env")

    config_path = Path(config_path) if config_path else PROJECT_ROOT / "config" / "config.yaml"
    if not config_path.exists():
        example = PROJECT_ROOT / "config" / "config.example.yaml"
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            f"Copy {example} to {config_path} and edit it first."
        )

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    cfg = AppConfig(
        printer=PrinterConfig(**raw.get("printer", {})),
        template=TemplateConfig(**raw.get("template", {})),
        database=DatabaseConfig(**raw.get("database", {})),
        sync=SyncConfig(**raw.get("sync", {})),
        logging=LoggingConfig(**raw.get("logging", {})),
    )
    cfg.supabase = SupabaseConfig(
        url=os.environ.get("SUPABASE_URL", ""),
        key=os.environ.get("SUPABASE_KEY", ""),
    )
    return cfg
