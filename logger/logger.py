import json
import logging
from datetime import datetime
from pathlib import Path

# Crear carpetas de logs y resultados si no existen
OUTPUTS_DIR = Path("outputs")
LOGS_DIR = Path("logs")
OUTPUTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Configuración del Logger en fichero y consola
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            LOGS_DIR / f"execution_{datetime.now():%Y%m%d}.log",
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)