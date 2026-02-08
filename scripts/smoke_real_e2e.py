#!/usr/bin/env python3
"""
Real-data smoke E2E test — uses actual YouTube + VK data via sync-sources.

NO real publishing — stops at ready_for_publish + dry-run plan.

Env vars:
  BASE_URL                     (default http://localhost:8000)
  OPS_KEY                      (optional, for prod/staging)
  TIMEOUT_SEC                  (default 900)
  POLL_INTERVAL                (default 5)
  REAL_TEST_PROJECT_ID         (optional — use existing project)
  REAL_TEST_YOUTUBE_ACCOUNT_ID (optional — for creating source)
  REAL_TEST_VK_ACCOUNT_ID      (optional — for creating source)
"""
from __future__ import annotations

import json
import os
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
OPS_KEY = os.environ.get("OPS_KEY", "")
TIMEOUT_SEC = int(os.environ.get("TIMEOUT_SEC", "900"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
REAL_PROJECT_ID = os.environ.get("REAL_TEST_PROJECT_ID", "")
REAL_YT_ACCOUNT = os.environ.get("REAL_TEST_YOUTUBE_ACCOUNT_ID", "")
REAL_VK_ACCOUNT = os.environ.get("REAL_TEST_VK_ACCOUNT_ID", "")

SMOKE_TAG = f"real_{int(time.time())}"

# ── Helpers ──────────────────────────────────────────────────

class SmokeError(Exception):
    pass


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if OPS_KEY:
        h["X-Ops-Key"] = OPS_KEY
    return h


def _req(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, headers=_headers(), method=method)
    try:
        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        raw = e.read().decode()[:500]
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


def step2_get_or_create_project() -> int:
    step("2. Get or create project")

    if REAL_PROJECT_ID:
        pid = int(REAL_PROJECT_ID)
        proj = GET(f"/api/projects/{pid}")
        ok(f"Using existing project #{pid}: {proj.get('name', '?')}")
    else:
        proj = POST("/api/projects", {
            "name": f"REAL SMOKE {SMOKE_TAG}",
            "status": "active",
            "mode": "MANUAL",
        })
        pid = proj["id"]
        ok(f"Created project #{pid}")

    # Ensure publish_settings via PATCH
    PATCH(f"/api/projects/{pid}", {
        "meta": {"publish_settings": {
            "publish_enabled": True,
            "timezone": "UTC",
            "windows": {d: [["00:00", "23:59"]] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]},
            "min_gap_minutes_per_destination": 1,
            "daily_limit_per_destination": 100,
        }},
    })
    ok("publish_settings configured in meta")
    return pid


def step3_ensure_sources_and_destinations(project_id: int):
    step("3. Ensure sources and destinations")

    # Check existing sources
    try:
        sources_data = GET(f"/api/projects/{project_id}/sources")
        # sources_data could be a list or dict
        existing_sources = sources_data if isinstance(sources_data, list) else sources_data.get("items", [])
    except SmokeError:
        existing_sources = []

    if existing_sources:
        ok(f"Project has {len(existing_sources)} existing sources")
    else:
        # Try to add YouTube and VK sources
        added = 0
        if REAL_YT_ACCOUNT:
            try:
                POST(f"/api/projects/{project_id}/sources", {
                    "platform": "YouTube",
                    "social_account_id": int(REAL_YT_ACCOUNT),
                })
                ok(f"Added YouTube source (account #{REAL_YT_ACCOUNT})")
                added += 1
            except SmokeError as e:
                print(f"  ⚠️  YouTube source: {e}")

        if REAL_VK_ACCOUNT:
            try:
                POST(f"/api/projects/{project_id}/sources", {
                    "platform": "VK",
                    "social_account_id": int(REAL_VK_ACCOUNT),
                })
                ok(f"Added VK source (account #{REAL_VK_ACCOUNT})")
                added += 1
            except SmokeError as e:
                print(f"  ⚠️  VK source: {e}")

        if added == 0 and not existing_sources:
            fail("No sources configured and no REAL_TEST_*_ACCOUNT_ID env vars set")

    # Check destinations
    try:
        dests = GET(f"/api/projects/{project_id}/destinations")
        dest_list = dests if isinstance(dests, list) else dests.get("items", [])
    except SmokeError:
        dest_list = []

    if dest_list:
        ok(f"Project has {len(dest_list)} destinations")
    else:
        ok("No destinations — will use default on approve")


def step4_sync_sources(project_id: int) -> dict:
    step("4. Sync sources into feed")
    result = POST(f"/api/projects/{project_id}/sync-sources")
    total_added = result.get("total_added", 0)
    total_updated = result.get("total_updated", 0)
    sources = result.get("sources", [])
    ok(f"Synced: +{total_added} new, ~{total_updated} updated, from {len(sources)} sources")
    for s in sources:
        print(f"    {s.get('platform')}: +{s.get('added', 0)} ~{s.get('updated', 0)}")
    return result


def step5_get_candidates(project_id: int) -> list:
    step("5. Fetch candidates from feed")

    all_candidates = []
    for platform in ["YouTube", "youtube", "VK", "vk", "TikTok", "tiktok"]:
        try:
            feed = GET(f"/api/projects/{project_id}/feed?platform={platform}&limit=50")
            items = feed if isinstance(feed, list) else feed.get("items", [])
            if items:
                ok(f"{platform}: {len(items)} candidates")
                all_candidates.extend(items)
        except SmokeError:
            pass

    # Also try without platform filter
    if not all_candidates:
        try:
            feed = GET(f"/api/projects/{project_id}/feed?limit=50")
            items = feed if isinstance(feed, list) else feed.get("items", [])
            all_candidates = items
            ok(f"All platforms: {len(items)} candidates")
        except SmokeError as e:
            fail(f"No candidates found: {e}")

    if not all_candidates:
        fail("No candidates in feed after sync")

    ok(f"Total candidates: {len(all_candidates)}")
    return all_candidates


def step6_pick_and_approve(project_id: int, candidates: list) -> tuple[int, int]:
    step("6. Pick best candidate and approve")

    # Filter only NEW candidates
    new_candidates = [c for c in candidates if c.get("status", "").upper() in ("NEW", "REJECTED")]
    if not new_candidates:
        # Try any non-approved
        new_candidates = [c for c in candidates if c.get("status", "").upper() not in ("APPROVED", "USED")]

    if not new_candidates:
        fail("No approvable candidates found (all already approved/used)")

    # Pick by max virality_score
    best = max(new_candidates, key=lambda c: c.get("virality_score") or 0)
    cid = best["id"]
    score = best.get("virality_score") or 0
    ok(f"Best candidate: #{cid} (score={score:.4f}, platform={best.get('platform')}, title={str(best.get('title', ''))[:50]})")

    # Approve
    result = POST(f"/api/projects/{project_id}/feed/{cid}/approve")
    task_id = result["task_id"]
    ok(f"Approved → Task #{task_id} (status={result.get('status')})")
    return cid, task_id


def step7_enqueue(task_id: int) -> str | None:
    step("7. Enqueue task for processing")

    celery_id = None
    try:
        result = POST(f"/api/publish-tasks/{task_id}/enqueue")
        celery_id = result.get("celery_task_id")
        ok(f"Enqueued via Celery: {celery_id}")
    except SmokeError as e:
        print(f"  ⚠️  Celery enqueue failed: {e}")
        print("  Trying fallback: process-v2...")
        try:
            POST(f"/api/publish-tasks/{task_id}/process-v2")
            ok("Fallback process-v2 started")
        except SmokeError as e2:
            fail(f"Both enqueue and process-v2 failed: {e2}")

    return celery_id


def step8_poll(task_id: int) -> str:
    step("8. Poll task until completion")

    deadline = time.time() + TIMEOUT_SEC
    final_statuses = {"done", "ready_for_review", "ready_for_publish", "error", "canceled"}
    last_status = "unknown"
    last_step_info = ""

    while time.time() < deadline:
        ui = GET(f"/api/publish-tasks/{task_id}/ui")
        last_status = ui["task"]["status"]

        # Show current step info
        steps = ui.get("steps", [])
        current_step = ""
        if steps:
            last_s = steps[-1]
            current_step = f"{last_s.get('tool_id', '?')}={last_s.get('status', '?')}"
            if current_step != last_step_info:
                last_step_info = current_step
                remaining = int(deadline - time.time())
                print(f"  ⏳ status={last_status}, step={current_step} (t-{remaining}s)")

        if last_status in final_statuses:
            break
        time.sleep(POLL_INTERVAL)
    else:
        fail(f"Timeout ({TIMEOUT_SEC}s) — last status: {last_status}, step: {last_step_info}")

    if last_status == "error":
        ui = GET(f"/api/publish-tasks/{task_id}/ui")
        error_msg = ui["task"].get("error_message") or ui["task"].get("publish_error") or "unknown"
        steps = ui.get("steps", [])
        print(f"\n  Error details:")
        print(f"    error_message: {error_msg[:200]}")
        if steps:
            for s in steps[-3:]:
                print(f"    step {s.get('tool_id')}: {s.get('status')} — {str(s.get('error_message', ''))[:100]}")
        fail(f"Task errored: {error_msg[:200]}")

    ok(f"Task reached status: {last_status}")
    return last_status


def step9_mark_ready(task_id: int) -> bool:
    step("9. Mark ready_for_publish")
    try:
        result = POST(f"/api/publish-tasks/{task_id}/mark-ready-for-publish")
        if result.get("ok"):
            ok(f"Status → {result.get('status')}")
            for c in result.get("checks", []):
                icon = "✅" if c["ok"] else "❌"
                print(f"    {icon} {c['check']}: {c['detail']}")
            return True
        else:
            print(f"  ⚠️  mark-ready-for-publish returned: {result}")
            return False
    except SmokeError as e:
        print(f"  ⚠️  mark-ready-for-publish failed: {e}")
        # Not fatal — task might not meet all criteria
        return False


def step9b_download(task_id: int):
    step("9b. Download final video")
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


def step10_dry_run_plan(project_id: int, task_id: int):
    step("10. Auto-publish DRY RUN (publish-plan)")
    try:
        plan = GET(f"/api/projects/{project_id}/publish-plan")
        dests = plan.get("destinations", [])
        total_slots = sum(len(d.get("slots", [])) for d in dests)
        total_skipped = sum(len(d.get("skipped", [])) for d in dests)

        found = False
        for d in dests:
            for slot in d.get("slots", []):
                if slot.get("task_id") == task_id:
                    found = True
                    ok(f"Task #{task_id} in plan slot: {slot.get('at')} score={slot.get('score')}")
            for skip in d.get("skipped", []):
                if skip.get("task_id") == task_id:
                    found = True
                    ok(f"Task #{task_id} skipped in plan: {skip.get('reason')}")

        ok(f"Plan: {total_slots} slots, {total_skipped} skipped, task found={found}")
        ok(f"Plan TZ={plan.get('timezone')}, date={plan.get('date')}, day={plan.get('day')}")
    except SmokeError as e:
        print(f"  ⚠️  publish-plan failed (non-fatal): {e}")


def step11_report(project_id, candidate_id, task_id, final_status, celery_id, ready_ok):
    step("11. Final Report")
    status_str = "ready_for_publish" if ready_ok else final_status
    print(f"""
  ┌──────────────────────────────────────────────────┐
  │  REAL SMOKE TEST REPORT                          │
  ├──────────────────────────────────────────────────┤
  │  Project ID:     {project_id:<33}│
  │  Candidate ID:   {candidate_id:<33}│
  │  Task ID:        {task_id:<33}│
  │  Celery ID:      {str(celery_id or 'N/A'):<33}│
  │  Final Status:   {status_str:<33}│
  │  Ready for Pub:  {str(ready_ok):<33}│
  │                                                  │
  │  Backend UI:     /api/publish-tasks/{task_id}/ui{' '*(20 - len(str(task_id)))}│
  │  Frontend UI:    /queue/{task_id}{' '*(28 - len(str(task_id)))}│
  │                                                  │
  │  RESULT:  ✅ PASS                                │
  └──────────────────────────────────────────────────┘
""")


# ── Main ─────────────────────────────────────────────────────

def main():
    print(f"\n🔬 Real-Data Smoke E2E Test — {BASE_URL}")
    print(f"   OPS_KEY={'set' if OPS_KEY else 'none'}  TIMEOUT={TIMEOUT_SEC}s  POLL={POLL_INTERVAL}s")
    print(f"   PROJECT={'#' + REAL_PROJECT_ID if REAL_PROJECT_ID else 'auto-create'}")
    print(f"   YT_ACCT={'#' + REAL_YT_ACCOUNT if REAL_YT_ACCOUNT else 'none'}  VK_ACCT={'#' + REAL_VK_ACCOUNT if REAL_VK_ACCOUNT else 'none'}\n")

    try:
        # 1. Health
        step1_health()

        # 2. Project
        project_id = step2_get_or_create_project()

        # 3. Sources & destinations
        step3_ensure_sources_and_destinations(project_id)

        # 4. Sync sources
        step4_sync_sources(project_id)

        # 5. Fetch candidates
        candidates = step5_get_candidates(project_id)

        # 6. Pick best + approve
        candidate_id, task_id = step6_pick_and_approve(project_id, candidates)

        # 7. Enqueue
        celery_id = step7_enqueue(task_id)

        # 8. Poll
        final_status = step8_poll(task_id)

        # 9. Mark ready
        ready_ok = step9_mark_ready(task_id)

        # 9b. Download final video
        step9b_download(task_id)

        # 10. Dry-run plan
        step10_dry_run_plan(project_id, task_id)

        # 11. Report
        step11_report(project_id, candidate_id, task_id, final_status, celery_id, ready_ok)

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
