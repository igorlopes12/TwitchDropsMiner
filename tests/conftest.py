import sys
from pathlib import Path

# constants.py derives the working directory (lang/, settings.json, ...) from sys.argv[0]
sys.argv[0] = str(Path(__file__).resolve().parent.parent / "main.py")
