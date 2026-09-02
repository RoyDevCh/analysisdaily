import os
import sys
from pathlib import Path

# 测试必须隔离于本地 .env 密钥与网络：强制规则引擎 + 确定性向量，禁用 LLM/DB。
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("LLM_BASE_URL", "")
os.environ.setdefault("EMBEDDING_BACKEND", "tfidf")
os.environ.setdefault("DATABASE_URL", "")

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
