"""Paths belong to each installation, never to the published repository."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
LOCAL=ROOT/'installation.local.json'
config=json.loads(LOCAL.read_text(encoding='utf-8')) if LOCAL.exists() else {}
WHALE_ROOT=Path(config.get('whale_root',ROOT/'WhaleGirl')).resolve()
MAIBOT_ROOT=Path(config.get('maibot_root',ROOT/'MaiBot')).resolve()
INSTANCE_ROOT=Path(config.get('instance_root',ROOT/'instance')).resolve()
MAIBOT_PYTHON=Path(config.get('maibot_python',MAIBOT_ROOT/'.venv/Scripts/python.exe')).resolve()
