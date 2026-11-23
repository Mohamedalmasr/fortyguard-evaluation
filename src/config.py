import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent

load_dotenv(ROOT_DIR / ".env")

API_KEY = os.getenv("FORTYGUARD_API_KEY")
API_URL = os.getenv("FORTYGUARD_API_URL")
MCP_URL = os.getenv("FORTYGUARD_MCP_URL")

if not API_KEY or not API_KEY.strip():
    raise ValueError("FORTYGUARD_API_KEY is missing from .env")

if not API_URL or not API_URL.strip() or not MCP_URL or not MCP_URL.strip():
    raise ValueError("FortyGuard URLs are missing from .env")
