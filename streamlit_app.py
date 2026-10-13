"""Compatibility entrypoint: always launch the authenticated dashboard."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().with_name("app.py")), run_name="__main__")
