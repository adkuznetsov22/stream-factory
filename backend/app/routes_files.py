from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

DATA_DIR = Path("/data")
TASKS_DIR = DATA_DIR / "tasks"
TASK_FILE_WHITELIST = {
    "raw.mp4",
    "ready.mp4",
    "final.mp4",
    "thumb.jpg",
    "preview.mp4",
    "probe.json",
    "process.log",
    "captions.srt",
}

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/tasks/{task_id}/{filename}")
async def get_task_file(task_id: int, filename: str):
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if filename not in TASK_FILE_WHITELIST:
        raise HTTPException(status_code=404, detail="File not allowed")
    path = TASKS_DIR / str(task_id) / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)
