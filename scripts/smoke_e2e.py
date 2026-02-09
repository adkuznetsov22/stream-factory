#!/usr/bin/env python3
"""
Smoke E2E test — validates the full pipeline on a clean database.

No external API tokens required. Uses a local sample.mp4 and a minimal
SMOKE_MIN preset that skips download/ffmpeg/whisper.

Env vars:
  BASE_URL       (default http://localhost:8000)
  OPS_KEY        (optional, for prod/staging)
  TIMEOUT_SEC    (default 300)
  POLL_INTERVAL  (default 3)
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
OPS_KEY = os.environ.get("OPS_KEY", "")
TIMEOUT_SEC = int(os.environ.get("TIMEOUT_SEC", "300"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "3"))

SMOKE_TAG = f"smoke_{int(time.time())}"

# ── Helpers ──────────────────────────────────────────────────

class SmokeError(Exception):
    pass


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if OPS_KEY:
        h["X-Ops-Key"] = OPS_KEY
    return h


def _req(method: str, path: str, body: dict | None = None, expect: int = 200) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, headers=_headers(), method=method)
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        raw = e.read().decode()[:500]
        if e.code == expect:
            return json.loads(raw) if raw else {}
        raise SmokeError(f"{method} {path} → {e.code}: {raw}")
    except URLError as e:
        raise SmokeError(f"{method} {path} → URLError: {e}")


def GET(path: str) -> dict:
    return _req("GET", path)


def POST(path: str, body: dict | None = None) -> dict:
    return _req("POST", path, body)


def PATCH(path: str, body: dict | None = None) -> dict:
    return _req("PATCH", path, body)


def step(name: str):
    print(f"\n{'='*60}")
    print(f"  STEP: {name}")
    print(f"{'='*60}")


def ok(msg: str):
    print(f"  ✅ {msg}")


def fail(msg: str):
    print(f"  ❌ {msg}")
    raise SmokeError(msg)


# ── Steps ────────────────────────────────────────────────────

def step1_health() -> dict:
    step("1. Health check")
    data = GET("/api/ops/health")
    pf = data.get("preflight", {})
    if pf.get("ok"):
        ok(f"Preflight OK (checks: {len(pf.get('checks', []))})")
    else:
        failed_checks = [c for c in pf.get("checks", []) if not c.get("ok")]
        fail(f"Preflight FAILED: {failed_checks}")
    return data


def step2_create_project(preset_id: int) -> int:
    step("2. Create SMOKE project")
    project = POST("/api/projects", {
        "name": f"SMOKE Project {SMOKE_TAG}",
        "status": "active",
        "mode": "MANUAL",
        "preset_id": preset_id,
    })
    pid = project["id"]
    ok(f"Project #{pid} created")

    # Set meta.publish_settings via PATCH (meta field only in ProjectUpdate)
    PATCH(f"/api/projects/{pid}", {
        "policy": {"qc_min_duration_sec": 0, "qc_min_resolution": 0},
        "meta": {"publish_settings": {
            "publish_enabled": True,
            "timezone": "UTC",
            "windows": {"mon": [["00:00","23:59"]], "tue": [["00:00","23:59"]],
                        "wed": [["00:00","23:59"]], "thu": [["00:00","23:59"]],
                        "fri": [["00:00","23:59"]], "sat": [["00:00","23:59"]],
                        "sun": [["00:00","23:59"]]},
            "min_gap_minutes_per_destination": 1,
            "daily_limit_per_destination": 100,
        }},
    })
    ok(f"Project meta.publish_settings configured")
    return pid


def step2b_create_preset() -> int:
    step("2b. Create SMOKE_MIN preset")
    # Create preset
    preset = POST("/api/presets", {"name": f"SMOKE_MIN_{SMOKE_TAG}", "description": "Minimal smoke test preset"})
    preset_id = preset["id"]
    ok(f"Preset #{preset_id} created")

    # Add steps: T17_PACKAGE → T18_QC (skip download/ffmpeg/whisper)
    POST(f"/api/presets/{preset_id}/steps", {
        "tool_id": "T17_PACKAGE", "name": "Package", "order_index": 0, "enabled": True, "params": {},
    })
    POST(f"/api/presets/{preset_id}/steps", {
        "tool_id": "T18_QC", "name": "Quality Check", "order_index": 1, "enabled": True,
        "params": {"min_duration_sec": 0, "min_resolution": 0},
    })
    ok(f"Preset steps: T17_PACKAGE, T18_QC")
    return preset_id


def step3_create_destination(project_id: int) -> int:
    step("3. Create destination (fake TikTok account)")
    # Create social account
    account = POST("/api/accounts", {
        "platform": "TikTok",
        "label": f"Smoke Account {SMOKE_TAG}",
        "login": f"smoke_{SMOKE_TAG}",
    })
    account_id = account["id"]
    ok(f"SocialAccount #{account_id} created")

    # Add as project destination
    dest = POST(f"/api/projects/{project_id}/destinations", {
        "platform": "TikTok",
        "social_account_id": account_id,
        "priority": 1,
    })
    dest_id = dest["id"]
    ok(f"Destination #{dest_id} (acct #{account_id})")
    return dest_id


def step4_create_candidate(project_id: int) -> int:
    step("4. Create candidate")
    cand = POST(f"/api/projects/{project_id}/feed", {
        "platform": "TikTok",
        "platform_video_id": f"smoke_vid_{SMOKE_TAG}",
        "origin": "REPURPOSE",
        "title": "Smoke Test Video",
        "caption": "Automated smoke test candidate",
        "url": "https://example.com/smoke",
        "views": 1000,
        "likes": 100,
        "virality_score": 0.75,
    })
    cid = cand["id"]
    ok(f"Candidate #{cid} (status={cand['status']})")
    return cid


def step5_approve(project_id: int, candidate_id: int) -> int:
    step("5. Approve candidate")
    result = POST(f"/api/projects/{project_id}/feed/{candidate_id}/approve")
    task_id = result["task_id"]
    ok(f"Approved → Task #{task_id} (status={result.get('status')})")
    return task_id


def step6_inject_video(task_id: int):
    """Inject sample.mp4 into task artifacts so pipeline can skip download."""
    step("6. Inject sample video into task artifacts")
    # Find sample.mp4
    candidates = [
        Path(__file__).parent.parent / "data" / "sample.mp4",
        Path("/data/sample.mp4"),
    ]
    sample = None
    for p in candidates:
        if p.exists():
            sample = p
            break

    if not sample:
        fail("sample.mp4 not found in data/ — run: ffmpeg -f lavfi -i 'color=c=blue:s=320x240:d=1' -f lavfi -i 'sine=frequency=440:d=1' -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -shortest data/sample.mp4")

    # Copy to task work dir
    task_dir = Path(f"/data/tasks/{task_id}")
    task_dir.mkdir(parents=True, exist_ok=True)
    dst = task_dir / "final.mp4"
    shutil.copy2(sample, dst)

    # Update task artifacts via direct PATCH (or we set it via PUT)
    # Use the publish-tasks UI endpoint to check current state
    ui = GET(f"/api/publish-tasks/{task_id}/ui")
    ok(f"Sample video injected: {dst} ({dst.stat().st_size} bytes)")
    ok(f"Task status: {ui['task']['status']}")


def step7_poll_or_mark_done(task_id: int) -> str:
    """
    Since we have a minimal preset, the task might need processing or
    we can manually set it to done if it's queued.
    For smoke: we'll try to enqueue and poll, but if celery isn't processing
    it quickly, we'll check if artifacts are there and force status.
    """
    step("7. Process task (enqueue + poll)")

    # Try enqueue
    try:
        enq = POST(f"/api/publish-tasks/{task_id}/enqueue")
        celery_id = enq.get("celery_task_id", "none")
        ok(f"Enqueued: celery_task_id={celery_id}")
    except SmokeError as e:
        ok(f"Enqueue skipped: {e}")

    # Poll for completion
    deadline = time.time() + TIMEOUT_SEC
    final_statuses = {"done", "ready_for_review", "ready_for_publish", "error", "canceled"}
    last_status = "unknown"

    while time.time() < deadline:
        ui = GET(f"/api/publish-tasks/{task_id}/ui")
        last_status = ui["task"]["status"]
        print(f"  ⏳ status={last_status} (t-{int(deadline - time.time())}s)", end="\r")

        if last_status in final_statuses:
            print()
            break
        time.sleep(POLL_INTERVAL)
    else:
        print()
        fail(f"Timeout ({TIMEOUT_SEC}s) — last status: {last_status}")

    if last_status == "error":
        error_msg = ui["task"].get("error_message") or ui["task"].get("publish_error") or "unknown"
        # Print last step results
        steps = ui.get("steps", [])
        if steps:
            last_step = steps[-1]
            print(f"  Last step: {last_step.get('tool_id')} → {last_step.get('status')}")
            if last_step.get("error_message"):
                print(f"  Error: {last_step['error_message'][:200]}")
        fail(f"Task errored: {error_msg[:200]}")

    ok(f"Task reached status: {last_status}")
    return last_status


def step8_mark_ready(task_id: int):
    step("8. Mark ready_for_publish")
    result = POST(f"/api/publish-tasks/{task_id}/mark-ready-for-publish")
    if result.get("ok"):
        ok(f"Status → {result.get('status')} (checks: {len(result.get('checks', []))})")
        for c in result.get("checks", []):
            icon = "✅" if c["ok"] else "❌"
            print(f"    {icon} {c['check']}: {c['detail']}")
    else:
        fail(f"mark-ready-for-publish failed: {result}")


def step8b_download(task_id: int):
    step("8b. Download final video")
    url = f"{BASE_URL}/api/publish-tasks/{task_id}/download"
    req = Request(url, headers=_headers(), method="GET")
    try:
        with urlopen(req, timeout=30) as resp:
            size = len(resp.read())
            ct = resp.headers.get("Content-Type", "")
            cd = resp.headers.get("Content-Disposition", "")
            if size > 0:
                ok(f"Download OK: {size} bytes, Content-Type={ct}")
                ok(f"Content-Disposition: {cd}")
            else:
                fail("Download returned empty body")
    except HTTPError as e:
        fail(f"Download failed: {e.code} {e.read().decode()[:200]}")
    except URLError as e:
        fail(f"Download failed: {e}")


def step8c_package(task_id: int):
    step("8c. Download package zip")
    url = f"{BASE_URL}/api/publish-tasks/{task_id}/package"
    req = Request(url, headers=_headers(), method="GET")
    try:
        with urlopen(req, timeout=60) as resp:
            data = resp.read()
            ct = resp.headers.get("Content-Type", "")
            if len(data) == 0:
                fail("Package returned empty body")
            ok(f"Package OK: {len(data)} bytes, Content-Type={ct}")
            # Verify zip contents
            import io, zipfile
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
                ok(f"Zip contents: {names}")
                if "metadata.json" not in names:
                    fail("metadata.json missing from package")
                has_video = any(n.endswith(".mp4") for n in names)
                if not has_video:
                    fail("No .mp4 file in package")
                ok("Package contains final.mp4 + metadata.json ✓")
    except HTTPError as e:
        fail(f"Package failed: {e.code} {e.read().decode()[:200]}")
    except URLError as e:
        fail(f"Package failed: {e}")


def step9_auto_publish_dry(project_id: int, task_id: int):
    step("9. Auto-publish DRY RUN (via publish-plan)")
    plan = GET(f"/api/projects/{project_id}/publish-plan")
    dests = plan.get("destinations", [])
    total_slots = sum(len(d.get("slots", [])) for d in dests)
    total_skipped = sum(len(d.get("skipped", [])) for d in dests)

    found = False
    for d in dests:
        for slot in d.get("slots", []):
            if slot.get("task_id") == task_id:
                found = True
                ok(f"Task #{task_id} found in plan slot: {slot.get('at')} score={slot.get('score')}")
        for skip in d.get("skipped", []):
            if skip.get("task_id") == task_id:
                found = True
                ok(f"Task #{task_id} skipped in plan: {skip.get('reason')}")

    ok(f"Plan: {total_slots} slots, {total_skipped} skipped, task found={found}")


def step10_report(project_id, candidate_id, task_id, final_status):
    step("10. Final Report")
    print(f"""
  ┌─────────────────────────────────────────────┐
  │  SMOKE TEST REPORT                          │
  ├─────────────────────────────────────────────┤
  │  Project ID:     {project_id:<27}│
  │  Candidate ID:   {candidate_id:<27}│
  │  Task ID:        {task_id:<27}│
  │  Final Status:   {final_status:<27}│
  │                                             │
  │  Backend UI:     /api/publish-tasks/{task_id}/ui{' '*(14 - len(str(task_id)))}│
  │  Frontend UI:    /queue/{task_id}{' '*(22 - len(str(task_id)))}│
  │                                             │
  │  RESULT:  ✅ PASS                           │
  └─────────────────────────────────────────────┘
""")


# ── Main ─────────────────────────────────────────────────────

def main():
    print(f"\n🔬 Smoke E2E Test — {BASE_URL}")
    print(f"   OPS_KEY={'set' if OPS_KEY else 'none'}  TIMEOUT={TIMEOUT_SEC}s  POLL={POLL_INTERVAL}s\n")

    try:
        # 1. Health
        step1_health()

        # 2b. Create preset first
        preset_id = step2b_create_preset()

        # 2. Create project
        project_id = step2_create_project(preset_id)

        # 3. Create destination
        step3_create_destination(project_id)

        # 4. Create candidate
        candidate_id = step4_create_candidate(project_id)

        # 5. Approve
        task_id = step5_approve(project_id, candidate_id)

        # 6. Inject video
        step6_inject_video(task_id)

        # 7. Enqueue + poll
        final_status = step7_poll_or_mark_done(task_id)

        # 8. Mark ready_for_publish
        step8_mark_ready(task_id)

        # 8b. Download final video
        step8b_download(task_id)

        # 8c. Download package
        step8c_package(task_id)

        # 9. Auto-publish dry run
        step9_auto_publish_dry(project_id, task_id)

        # 10. Report
        step10_report(project_id, candidate_id, task_id, "ready_for_publish")

    except SmokeError as e:
        print(f"\n{'='*60}")
        print(f"  ❌ FAIL: {e}")
        print(f"{'='*60}\n")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n  ⏹ Interrupted")
        sys.exit(130)


if __name__ == "__main__":
    main()
