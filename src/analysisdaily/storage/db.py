"""可选的 PostgreSQL/pgvector 存储层（本地 docker 容器）。

默认不启用：仅当 DATABASE_URL 可连且 `psycopg` 已安装时才会初始化并写库；
否则静默跳过，管道继续用文件/内存后端。容器用 `docker compose up -d` 启动。
"""
from __future__ import annotations

import json
import logging
import re

from ..config import Settings
from ..models.raw import RawArticle
from ..models.report import StructuredReport

logger = logging.getLogger("analysisdaily")


def _plain_url(dsn: str) -> str:
    # 兼容 sqlalchemy 风格 postgresql+pgvector:// -> postgresql://
    return re.sub(r"postgresql\+\w+://", "postgresql://", dsn)


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._conn = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.database_url)

    def connect(self):
        if self._conn is not None:
            return True
        if not self.enabled:
            return False
        import importlib.util

        if importlib.util.find_spec("psycopg") is None:
            logger.info("psycopg 未安装，跳过 Postgres 存储（pip install -e .[db] 可启用）")
            return False
        try:
            import psycopg  # type: ignore

            self._conn = psycopg.connect(_plain_url(self.settings.database_url), connect_timeout=5)
            self._init_schema()
            return True
        except Exception:  # noqa: BLE001
            logger.warning("Postgres 不可用，跳过 DB 存储（docker compose up -d 后重试）")
            self._conn = None
            return False

    def _init_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    id text PRIMARY KEY,
                    source_name text, channel text, bias text, side text,
                    title text, url text, published timestamptz,
                    content text, fetched_at timestamptz
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    event_id text PRIMARY KEY,
                    date date, category text, headline text,
                    data jsonb, generated_at timestamptz
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS reports_date_idx ON reports(date);")
        self._conn.commit()

    def store_article(self, a: RawArticle) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO articles
                (id, source_name, channel, bias, side, title, url, published, content, fetched_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING;""",
                (
                    a.id, a.source_name, a.channel.value, a.bias.value, a.side,
                    a.title, a.url, a.published, a.content, a.fetched_at,
                ),
            )
        self._conn.commit()

    def store_report(self, r: StructuredReport) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO reports (event_id, date, category, headline, data, generated_at)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (event_id) DO UPDATE SET data = EXCLUDED.data;""",
                (r.event_id, r.date, r.category, r.headline, json.dumps(r.to_render_dict()), r.generated_at),
            )
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def get_db(settings: Settings) -> Database:
    return Database(settings)