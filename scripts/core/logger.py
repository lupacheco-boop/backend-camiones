"""Configuración de logs combinados por fecha para auditoría y trazabilidad del servidor."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from scripts.core.config import BASE_DIR

LOGS_DIR: Path = BASE_DIR / "logs"
LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class LoggerManager:
    """Gestor POO centralizado para registro de eventos en consola y archivos .log diarios combinados."""

    _configured: bool = False

    @classmethod
    def get_daily_log_file(cls) -> Path:
        """Obtiene la ruta del archivo de log del día actual (formato: logs/YYYYMMDD.log)."""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        return LOGS_DIR / f"{date_str}.log"

    @classmethod
    def setup_logging(cls, level: int = logging.INFO) -> logging.Logger:
        """Inicializa los handlers de consola y archivo único diario en `logs/<YYYYMMDD>.log`."""
        root_logger = logging.getLogger("camiones_backend")
        if cls._configured:
            return root_logger

        root_logger.setLevel(level)
        formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

        # Handler de consola (stdout)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)

        # Handler de archivo único diario rotativo (10 MB por archivo, hasta 5 respaldos)
        daily_log_file = cls.get_daily_log_file()
        file_handler = RotatingFileHandler(
            filename=daily_log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)

        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
        root_logger.propagate = False

        cls._configured = True
        return root_logger

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Obtiene un logger hijo bajo el namespace del proyecto."""
        if not cls._configured:
            cls.setup_logging()
        return logging.getLogger(f"camiones_backend.{name}")


logger = LoggerManager.get_logger("core")
