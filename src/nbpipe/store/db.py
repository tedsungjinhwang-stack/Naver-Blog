"""SQLite 기반 실행 로그.

생성한 초안의 메타(니치/키워드/점수/파일경로)를 기록해 중복 주제 방지와
성과 추적에 쓴다. DB 파일은 기본 data/nbpipe.sqlite3 (gitignore 처리).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,
    niche        TEXT NOT NULL,
    primary_keyword TEXT NOT NULL,
    title        TEXT,
    char_count   INTEGER,
    seo_score    INTEGER,
    compliance_ok INTEGER,
    tags         TEXT,
    files        TEXT,
    meta         TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_keyword ON runs(primary_keyword);
CREATE INDEX IF NOT EXISTS idx_runs_niche ON runs(niche);
"""


class RunStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record(
        self,
        *,
        niche: str,
        primary_keyword: str,
        title: str,
        char_count: int,
        seo_score: int,
        compliance_ok: bool,
        tags: list[str],
        files: list[str],
        meta: dict[str, Any] | None = None,
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO runs (created_at, niche, primary_keyword, title,
                              char_count, seo_score, compliance_ok, tags, files, meta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                niche,
                primary_keyword,
                title,
                char_count,
                seo_score,
                1 if compliance_ok else 0,
                json.dumps(tags, ensure_ascii=False),
                json.dumps(files, ensure_ascii=False),
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def recent_keywords(self, niche: str | None = None, limit: int = 200) -> list[str]:
        """최근 다룬 핵심 키워드(중복 주제 회피용)."""
        if niche:
            rows = self._conn.execute(
                "SELECT primary_keyword FROM runs WHERE niche=? "
                "ORDER BY id DESC LIMIT ?",
                (niche, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT primary_keyword FROM runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [r["primary_keyword"] for r in rows]

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "RunStore":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()
