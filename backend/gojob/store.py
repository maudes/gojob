"""Everything lives in one local JSON file. Nothing leaves this machine except model calls."""
from __future__ import annotations

import copy
import json
import os
import random
import string
import threading
import time
from typing import Any, Callable, TypeVar

from . import config
from .schemas import Profile

T = TypeVar("T")

EMPTY_COACH = {"storyBank": {"text": "", "name": "", "updatedAt": None}, "items": [], "report": None}
EMPTY_SCOUT = {"settings": None, "report": None, "history": [], "wishlist": [], "companies": []}


def empty_db() -> dict:
    return {
        "schemaVersion": config.SCHEMA_VERSION,
        "profile": Profile().dump(),
        "health": None,
        "healthRuns": 0,
        "analyses": [],
        "tracker": [],
        "feedback": [],
        "coach": copy.deepcopy(EMPTY_COACH),
        "scout": copy.deepcopy(EMPTY_SCOUT),
    }


# Each entry upgrades a database from the previous version. Add one whenever SCHEMA_VERSION goes up.
MIGRATIONS: dict[int, Callable[[dict], None]] = {
    # 1: databases from before versioning existed (the Next.js version). Nothing to rewrite;
    #    the file is only stamped, and older results simply have no `meta`.
    1: lambda db: None,
}


def migrate(db: dict) -> dict:
    version = db.get("schemaVersion", 0)
    if version > config.SCHEMA_VERSION:
        raise RuntimeError(
            f"data/db.json was written by a newer Go Job (data version {version}, this one knows {config.SCHEMA_VERSION}). Update the app instead of opening it with this version."
        )
    while version < config.SCHEMA_VERSION:
        version += 1
        MIGRATIONS[version](db)
    db["schemaVersion"] = version
    return db


_lock = threading.RLock()


def _load_raw() -> dict | None:
    try:
        raw = config.DB_FILE.read_text("utf8")
    except FileNotFoundError:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        # Never overwrite a damaged file: keep it aside and start clean.
        config.DB_FILE.rename(config.DB_FILE.with_name(f"db.corrupt-{int(time.time())}.json"))
        return None


def read_db() -> dict:
    with _lock:
        raw = _load_raw()
        if raw is None:
            return empty_db()
        old_version = raw.get("schemaVersion", 0)
        base = empty_db()
        db = {**base, **raw}
        db["profile"] = {**base["profile"], **(raw.get("profile") or {})}
        db["coach"] = {**base["coach"], **(raw.get("coach") or {})}
        db["scout"] = {**base["scout"], **(raw.get("scout") or {})}
        db["schemaVersion"] = old_version
        if old_version < config.SCHEMA_VERSION:
            backup = config.DB_FILE.with_name(f"db.v{old_version}.bak.json")
            if not backup.exists():
                backup.write_text(json.dumps(raw, indent=2, ensure_ascii=False), "utf8")
        return migrate(db)


def update_db(fn: Callable[[dict], T]) -> T:
    """Serialised read-modify-write so parallel requests cannot clobber each other."""
    with _lock:
        db = read_db()
        result = fn(db)
        config.DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = config.DB_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(db, indent=2, ensure_ascii=False), "utf8")
        os.replace(tmp, config.DB_FILE)
        return result


def new_id() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def get(d: dict, *path: str, default: Any = None) -> Any:
    for key in path:
        if not isinstance(d, dict) or key not in d:
            return default
        d = d[key]
    return d
