# config.py
# ここに設定を記載します

import os

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5-nano")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", 1536))
AI_URL = "http://host.docker.internal:11434"

DB_HOST = os.getenv("DB_HOST", "db")
DB_USER = os.getenv("DB_USER", "me")
DB_PASSWORD = os.getenv("DB_PASSWORD", "me")
DB_NAME = os.getenv("DB_NAME", "mydb")
DB_PORT = int(os.getenv("DB_PORT", 3306))
