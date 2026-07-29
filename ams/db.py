import json
import os
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "db.json"


@dataclass(frozen=True)
class DbError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


def _ensure_db_exists() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        return
    # Minimal seed; full seed will be expanded by ensure_seed().
    DB_PATH.write_text(
        json.dumps(
            {
                "meta": {"version": 1, "created_at": int(time.time())},
                "settings": {
                    "active_year": "2025/2026",
                    "active_term": "ganjil",
                    "krs_open": True,
                    "kuliah_open": False,
                    "nilai_open": False,
                },
                "users": [],
                "jurusan": [],
                "dosen": [],
                "mahasiswa": [],
                "matakuliah": [],
                "offering": [],
                "krs": [],
                "enrollments": [],
                "bimbingan": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def load_db() -> dict[str, Any]:
    _ensure_db_exists()
    return json.loads(DB_PATH.read_text(encoding="utf-8"))


def save_db(db: dict[str, Any]) -> None:
    _ensure_db_exists()
    tmp = str(DB_PATH) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
    os.replace(tmp, DB_PATH)


def update_db(mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    db = load_db()
    db2 = deepcopy(db)
    mutator(db2)
    save_db(db2)
    return db2


def next_id(items: list[dict[str, Any]]) -> int:
    return (max((x.get("id", 0) for x in items), default=0) or 0) + 1

