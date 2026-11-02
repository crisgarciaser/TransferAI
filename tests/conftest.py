"""Permite que las pruebas importen los módulos del proyecto desde la carpeta raíz."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
