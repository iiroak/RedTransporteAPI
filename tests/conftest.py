"""Aislamiento del entorno para toda la suite.

red_transporte_api.config lee las variables de entorno en tiempo de import,
así que hay que fijarlas aquí, antes de importar cualquier módulo del paquete.
Sin esto, los tests de integración escribirían en ~/.red_transporte del usuario
y heredarían la política del .env local.
"""

import atexit
import os
import shutil
import tempfile

_DATA_DIR = tempfile.mkdtemp(prefix="red-transporte-tests-")

os.environ["RED_TRANSPORTE_DATA_DIR"] = _DATA_DIR
os.environ["RED_TRANSPORTE_PUBLIC_API"] = "true"
os.environ["RED_TRANSPORTE_MASTER_TOKEN"] = "test-master-token"
os.environ["RED_TRANSPORTE_DB_BACKEND"] = "sqlite"
os.environ["RED_TRANSPORTE_TRUST_PROXY"] = "false"


def _cleanup() -> None:
    shutil.rmtree(_DATA_DIR, ignore_errors=True)


atexit.register(_cleanup)
