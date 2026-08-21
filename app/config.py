"""Configuration loading.

Non-secret, machine-specific settings live in config/config.yaml
(copied from config.example.yaml). Secrets (Supabase URL/key) live in
.env and are never written into config.yaml or source control.
"""
from __future__ import annotations

import os
import shutil
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
class WebConfig:
    # 0.0.0.0 so other devices on the local university network (the
    # public display screen, a tablet used to call numbers) can reach
    # it at http://<this-pc-ip>:<port> — not just localhost.
    host: str = "0.0.0.0"
    port: int = 8000
    next_numbers_count: int = 5


@dataclass
class AppConfig:
    printer: PrinterConfig = field(default_factory=PrinterConfig)
    template: TemplateConfig = field(default_factory=TemplateConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    supabase: SupabaseConfig = field(default_factory=SupabaseConfig)
    web: WebConfig = field(default_factory=WebConfig)
    # Which of the four buildings (B/C/E/F — see core/certificates.py's
    # BUILDINGS list) this specific desktop install serves. Empty until
    # the employee picks one on first run (see ui/building_dialog.py);
    # persisted here (not .env) because it's a per-machine identity
    # setting, not a secret, same category as the printer name below.
    # One install == one building, by design (see PLAN_MULTI_BUILDING.md)
    # — this is a single value, not a list.
    building: str = ""
    # "printer" (render + send to a real printer) or "preprinted" (the
    # employee already has numbered tickets on paper; the app just
    # tracks which number is next). Empty until chosen on first run —
    # see ui/print_mode_dialog.py. Same per-machine-identity category
    # as `building` above, not a secret.
    print_mode: str = ""
    # Where this config was loaded from — save_config() writes back here.
    # Not read from the YAML file itself.
    config_path: Path = field(default=None)

    def resolve_path(self, relative: str) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else PROJECT_ROOT / p


def load_config(config_path: str | Path | None = None) -> AppConfig:
    load_dotenv(PROJECT_ROOT / ".env")

    config_path = Path(config_path) if config_path else PROJECT_ROOT / "config" / "config.yaml"
    if not config_path.exists():
        # Every value in config.example.yaml is already a safe default
        # (printer name "" just means "no override yet" — the UI's
        # printer picker fills that in and persists it via
        # save_config()) so a first run on a new machine should just
        # work, not force a manual copy/edit step before the app will
        # even open.
        example = PROJECT_ROOT / "config" / "config.example.yaml"
        if not example.exists():
            raise FileNotFoundError(
                f"Config file not found: {config_path}\n"
                f"config.example.yaml is also missing from {example.parent} — reinstall the app."
            )
        config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(example, config_path)

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    cfg = AppConfig(
        printer=PrinterConfig(**raw.get("printer", {})),
        template=TemplateConfig(**raw.get("template", {})),
        database=DatabaseConfig(**raw.get("database", {})),
        sync=SyncConfig(**raw.get("sync", {})),
        logging=LoggingConfig(**raw.get("logging", {})),
        web=WebConfig(**raw.get("web", {})),
        building=raw.get("building", "") or "",
        print_mode=raw.get("print_mode", "") or "",
    )
    cfg.supabase = SupabaseConfig(
        url=os.environ.get("SUPABASE_URL", ""),
        key=os.environ.get("SUPABASE_KEY", ""),
    )
    cfg.config_path = config_path
    return cfg


def save_config(cfg: AppConfig) -> None:
    """Persists the (non-secret) settings back to config.yaml — used by
    the printer picker in the UI so a chosen printer survives restarts
    instead of reverting to whatever Windows currently calls the
    default printer, and by the building picker (ui/building_dialog.py)
    so this device's building selection survives restarts too. Secrets
    (Supabase URL/key) are never written here; they stay in .env."""
    path = cfg.config_path or (PROJECT_ROOT / "config" / "config.yaml")
    data = {
        "printer": {"name": cfg.printer.name, "copies": cfg.printer.copies},
        "template": {"path": cfg.template.path, "number_padding": cfg.template.number_padding},
        "database": {"path": cfg.database.path},
        "sync": {
            "enabled": cfg.sync.enabled,
            "interval_seconds": cfg.sync.interval_seconds,
            "batch_size": cfg.sync.batch_size,
        },
        "logging": {"dir": cfg.logging.dir, "level": cfg.logging.level},
        "web": {
            "host": cfg.web.host,
            "port": cfg.web.port,
            "next_numbers_count": cfg.web.next_numbers_count,
        },
        "building": cfg.building,
        "print_mode": cfg.print_mode,
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
