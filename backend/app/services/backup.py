"""
Postgres backup service — pg_dump with rotation.

Uses DATABASE_URL to extract connection params.
Stores dumps in BACKUP_DIR, keeps last BACKUP_KEEP_LAST files.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _parse_db_url(url: str) -> dict[str, str]:
    """Extract host, port, user, password, dbname from DATABASE_URL."""
    # Strip async driver prefix
    clean = re.sub(r"^postgresql\+\w+://", "postgresql://", url)
    parsed = urlparse(clean)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "dbname": parsed.path.lstrip("/") or "stream_factory",
    }


async def run_backup() -> dict[str, Any]:
    """Run pg_dump and rotate old backups."""
    from app.settings import get_settings
    settings = get_settings()

    backup_dir = Path(settings.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    db = _parse_db_url(settings.database_url)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{ts}.sql.gz"
    filepath = backup_dir / filename

    env = {"PGPASSWORD": db["password"]}
    cmd = [
        "pg_dump",
        "-h", db["host"],
        "-p", db["port"],
        "-U", db["user"],
        "-d", db["dbname"],
        "--no-owner",
        "--no-acl",
    ]

    try:
        # pg_dump | gzip > file
        proc_dump = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**__import__("os").environ, **env},
        )
        proc_gzip = await asyncio.create_subprocess_exec(
            "gzip",
            stdin=proc_dump.stdout,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        gz_data, gz_err = await asyncio.wait_for(proc_gzip.communicate(), timeout=600)
        await proc_dump.wait()

        if proc_dump.returncode != 0:
            _, dump_err = await proc_dump.communicate()
            return {"ok": False, "error": f"pg_dump failed: {(dump_err or b'').decode()[:300]}"}

        filepath.write_bytes(gz_data)
        size_mb = round(len(gz_data) / (1024 * 1024), 2)

        logger.info(f"[backup] Created {filename} ({size_mb} MB)")

    except asyncio.TimeoutError:
        return {"ok": False, "error": "pg_dump timeout (600s)"}
    except FileNotFoundError:
        return {"ok": False, "error": "pg_dump not found in PATH"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}

    # Rotate old backups
    rotated = _rotate(backup_dir, settings.backup_keep_last)

    return {
        "ok": True,
        "file": filename,
        "size_mb": size_mb,
        "rotated": rotated,
        "backup_dir": str(backup_dir),
    }


def _rotate(backup_dir: Path, keep: int) -> int:
    """Delete oldest backups beyond keep limit. Returns count deleted."""
    files = sorted(backup_dir.glob("backup_*.sql*"), key=lambda f: f.stat().st_mtime, reverse=True)
    deleted = 0
    for f in files[keep:]:
        try:
            f.unlink()
            deleted += 1
            logger.info(f"[backup] Rotated old backup: {f.name}")
        except Exception as e:
            logger.warning(f"[backup] Failed to delete {f.name}: {e}")
    return deleted
