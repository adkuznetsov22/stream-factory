"""Admin panel API: served by uvicorn inside the same event loop as the pipeline."""
import asyncio
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import policy
from .config import EDITABLE, SECRET_FIELDS
from .publish import CAPTIONS, CHECKS, FIELDS, TESTS
from .render import LAYOUTS
from .titles import make_meta

if TYPE_CHECKING:
    from .app import App

STATIC = Path(__file__).parent / "static"
MASK = "••••"
COOKIE = "lc_admin"


def mask(key: str, value):
    return MASK + str(value)[-4:] if key in SECRET_FIELDS and value else value


def unmask(new: dict, old: dict) -> dict:
    return {k: (old.get(k) if isinstance(v, str) and v.startswith(MASK) else v) for k, v in new.items()}


def status(app: "App") -> dict:
    now = time.time()
    s = app.s
    targets = []
    for t in app.store.targets():
        plan = app.publisher.plan(t)
        targets.append({"id": t["id"], "name": t["name"], "kind": t["kind"], "enabled": t["enabled"], "mode": t["mode"],
                        "daily_limit": t["daily_limit"], "check_ok": t["check_ok"], **plan})
    channels = []
    for login, ch in sorted(app.channels.items(), key=lambda kv: -kv[1].stream.viewers):
        prof = app.profile(login)
        hist = list(ch.detector.history)[-300:]
        channels.append({
            "login": login, "name": ch.stream.display_name, "title": ch.stream.title, "game": ch.stream.game,
            "avatar": ch.stream.avatar, "viewers": ch.stream.viewers, "list": prof.get("list", "auto"),
            "since": ch.started, "buffered_s": len(ch.recorder.segments) * s.segment_seconds,
            "recording": now - ch.recorder.latest_wall < 15, "warming": now - ch.started < s.warmup_seconds,
            "score": round(ch.detector.last_score, 2), "chat_z": round(ch.detector.last_parts[0], 2),
            "audio_z": round(ch.detector.last_parts[1], 2), "threshold": round(ch.detector.threshold, 2),
            "chat_per_min": sum(1 for m in ch.chat.messages if m[0] > now - 60),
            "history": [[h[0], h[1]] for h in hist[::2]], "moments": list(ch.detector.moments),
            "preview_at": ch.last_preview,
        })
    day = app.store.row(
        "SELECT COUNT(*) AS clips, COALESCE(SUM(status = 'published'), 0) AS published, "
        "COALESCE(SUM(status = 'error'), 0) AS errors, COALESCE(SUM(duplicate_of IS NOT NULL), 0) AS duplicates "
        "FROM clips WHERE created_at > ?", now - 86400)
    pending = app.store.row(
        "SELECT COUNT(*) AS n FROM clips c WHERE status = 'ready' AND path IS NOT NULL AND created_at > ? AND NOT EXISTS "
        "(SELECT 1 FROM publications p WHERE p.clip_id = c.id)", now - 86400)["n"]
    posts = app.store.row("SELECT COUNT(*) AS n FROM publications WHERE status = 'done' AND done_at > ?",
                          now - 86400)["n"]
    return {"ts": now, "channels": channels, "trigger_score": s.trigger_score, "queue": app.queue.qsize(),
            "rendering": sorted(app.rendering), "publish_paused": s.publish_paused, "day": {**day, "posts": posts},
            "pending_review": pending, "targets": targets, "disk": app.monitor.disk(),
            "alerts": bool(s.alerts_chat_id), "auto_discover": s.auto_discover, "whitelist": s.whitelist}


def create_api(app: "App") -> FastAPI:
    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    store = app.store

    def make_token() -> str:
        nonce = store.get_settings().get("_session_nonce")
        if not nonce:
            nonce = secrets.token_hex(16)
            store.set_settings({"_session_nonce": nonce})
        return hmac.new(app.admin_password.encode(), nonce.encode(), hashlib.sha256).hexdigest()

    api.state.token = make_token()
    store = app.store

    @api.middleware("http")
    async def auth(request: Request, call_next):
        path = request.url.path
        if (path.startswith("/api/") or path.startswith("/media/")) and path != "/api/login":
            token = api.state.token
            if not hmac.compare_digest(request.cookies.get(COOKIE, ""), token):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    @api.post("/api/login")
    async def login(request: Request, password: str = Body(embed=True)):
        if not hmac.compare_digest(password, app.admin_password):
            await asyncio.sleep(1)
            raise HTTPException(401, "неверный пароль")
        resp = JSONResponse({"ok": True})
        resp.set_cookie(COOKIE, api.state.token, max_age=30 * 86400, httponly=True, samesite="lax",
                        secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https")
        return resp

    @api.post("/api/logout")
    async def logout():
        store.set_settings({"_session_nonce": secrets.token_hex(16)})
        api.state.token = make_token()
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE)
        return resp

    @api.get("/api/status")
    async def get_status():
        return status(app)

    @api.get("/api/events")
    async def events(request: Request):
        async def gen():
            while not await request.is_disconnected():
                yield f"data: {json.dumps(status(app), ensure_ascii=False)}\n\n"
                await asyncio.sleep(2)
        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    # ---- clips ----
    def clip_out(c: dict, full: bool = False) -> dict:
        out = {k: v for k, v in c.items() if full or k not in ("transcript", "subs")}
        if not full and out.get("reasons"):
            out["reasons"] = {k: v for k, v in out["reasons"].items() if k not in ("hype", "chat_sample")}
        d = Path(c["path"]).parent if c["path"] else None
        out["has_file"] = bool(d and (d / "clip.mp4").exists())
        out["has_source"] = bool(c.get("src_path") and Path(c["src_path"]).exists())
        out["has_source_preview"] = bool(d and (d / "source.mp4").exists())
        out["publications"] = store.rows("SELECT * FROM publications WHERE clip_id = ? ORDER BY id", c["id"])
        prof = app.profile(c["login"])
        out["streamer"] = {"name": prof.get("display_name") or c["login"], "avatar": prof.get("avatar")}
        return out

    def get_clip(clip_id: int) -> dict:
        c = store.clip(clip_id)
        if not c:
            raise HTTPException(404, "клип не найден")
        return c

    @api.get("/api/clips")
    async def clips(view: str = "", login: str = "", limit: int = 40, before: int = 0, min_score: float = 0,
                    sort: str = "new"):
        where, args = ["score >= ?"], [min_score]
        views = {
            "review": "status = 'ready' AND path IS NOT NULL AND NOT EXISTS (SELECT 1 FROM publications p WHERE p.clip_id = clips.id)",
            "published": "status = 'published'", "rejected": "status = 'rejected'", "errors": "status = 'error'",
            "processing": "status IN ('detected', 'rendering')", "duplicates": "duplicate_of IS NOT NULL",
        }
        if view in views:
            where.append(views[view])
        if login:
            where.append("login = ?")
            args.append(login)
        if before:
            where.append("id < ?")
            args.append(before)
        order = "score DESC, id DESC" if sort == "score" else "id DESC"
        rows = store.rows(f"SELECT * FROM clips WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ?", *args, min(limit, 200))
        counts = {k: store.row(f"SELECT COUNT(*) AS n FROM clips WHERE {v} AND created_at > ?", time.time() - 86400)["n"]
                  for k, v in views.items()}
        return {"items": [clip_out(r) for r in rows], "counts": counts}

    @api.get("/api/clips/{clip_id}")
    async def clip(clip_id: int):
        out = clip_out(get_clip(clip_id), full=True)
        out["posts"] = {t["id"]: app.publisher.post_for(t, out) for t in store.targets()}
        out["decisions"] = {t["id"]: policy.decide(t.get("policy"), out) for t in store.targets()}
        return out

    @api.patch("/api/clips/{clip_id}")
    async def edit_clip(clip_id: int, body: dict = Body()):
        c = get_clip(clip_id)
        meta = c["meta"] or {}
        for k, n in (("title", 100), ("description", 4000), ("overlay", 80)):
            if k in body and body[k] is not None:
                meta[k] = str(body[k])[:n]
        store.update(clip_id, meta=meta, title=meta.get("title"))
        return await clip(clip_id)

    @api.post("/api/clips/{clip_id}/retitle")
    async def retitle(clip_id: int):
        c = get_clip(clip_id)
        prof = app.profile(c["login"])
        meta = await make_meta(app.http, app.s, c["login"], prof.get("display_name") or c["login"],
                               c.get("stream_title") or "", c["transcript"] or "", (c["reasons"] or {}).get("chat_sample", []))
        store.update(clip_id, meta={**(c["meta"] or {}), "title": meta["title"], "description": meta["description"]},
                     title=meta["title"])
        return await clip(clip_id)

    @api.post("/api/clips/{clip_id}/render")
    async def rerender(clip_id: int, body: dict = Body()):
        c = get_clip(clip_id)
        if not c["src_path"] or not Path(c["src_path"]).exists():
            raise HTTPException(400, "исходник уже удалён: менять можно только заголовок и описание")
        if c["status"] in ("detected", "rendering"):
            raise HTTPException(409, "клип уже собирается")
        e = dict(c["edit"] or {})
        dur = c["src_duration"] or 0
        ts, te = float(body.get("trim_start", e["trim_start"])), float(body.get("trim_end", e["trim_end"]))
        ts, te = max(0.0, ts), min(dur, te)
        if te - ts < 3:
            raise HTTPException(400, "клип короче 3 секунд")
        if te - ts > 90:
            raise HTTPException(400, "клип длиннее 90 секунд")
        e.update(trim_start=round(ts, 2), trim_end=round(te, 2))
        for k in ("overlay", "subtitles", "layout", "facecam"):
            if k in body:
                e[k] = body[k]
        if e.get("layout") and e["layout"] not in LAYOUTS:
            raise HTTPException(400, "неизвестная раскладка")
        if "subs" in body:
            store.update(clip_id, subs=[{"start": float(x["start"]), "end": float(x["end"]), "text": str(x["text"])}
                                        for x in body["subs"]])
        if "overlay" in body:
            store.update(clip_id, meta={**(c["meta"] or {}), "overlay": body["overlay"]})
        app.rerender(clip_id, e)
        return await clip(clip_id)

    @api.post("/api/clips/{clip_id}/publish")
    async def publish_clip(clip_id: int, target_ids: list[int] = Body(embed=True)):
        c = get_clip(clip_id)
        if not c["path"]:
            raise HTTPException(400, "файл клипа уже удалён")
        for tid in target_ids:
            if not store.add_publication(clip_id, tid):
                store.execute("UPDATE publications SET status = 'queued', error = NULL, created_at = ? "
                              "WHERE clip_id = ? AND target_id = ? AND status IN ('error', 'deleted')",
                              time.time(), clip_id, tid)
        if c["status"] == "rejected":
            store.update(clip_id, status="ready")
        return await clip(clip_id)

    @api.post("/api/clips/{clip_id}/reject")
    async def reject(clip_id: int):
        get_clip(clip_id)
        store.update(clip_id, status="rejected")
        store.execute("DELETE FROM publications WHERE clip_id = ? AND status = 'queued'", clip_id)
        return {"ok": True}

    @api.post("/api/clips/{clip_id}/restore")
    async def restore(clip_id: int):
        get_clip(clip_id)
        store.update(clip_id, status="ready", duplicate_of=None)
        return await clip(clip_id)

    @api.get("/media/preview/{login}.jpg")
    async def preview(login: str):
        f = app.previews / f"{login.lower()}.jpg"
        if not f.exists():
            raise HTTPException(404)
        return FileResponse(f, headers={"Cache-Control": "no-cache"})

    @api.get("/media/{clip_id}/{name}")
    async def media(clip_id: int, name: str):
        c = get_clip(clip_id)
        if name not in ("clip.mp4", "thumb.jpg", "source.mp4") or not c["path"]:
            raise HTTPException(404)
        f = Path(c["path"]).parent / name
        if not f.exists():
            raise HTTPException(404)
        return FileResponse(f, headers={"Cache-Control": "no-cache"})

    # ---- live ----
    @api.post("/api/channels/{login}/clip")
    async def clip_now(login: str, seconds: float = Body(30, embed=True)):
        try:
            return {"clip_id": app.manual_clip(login, max(5.0, min(seconds, app.s.buffer_seconds - 10)))}
        except KeyError:
            raise HTTPException(404, "стрим не пишется")

    @api.get("/api/channels/{login}/chat")
    async def chat(login: str):
        ch = app.channels.get(login)
        return [[ts, m] for ts, m in list(ch.chat.messages)[-60:]] if ch else []

    # ---- publications ----
    @api.get("/api/publications")
    async def publications(target_id: int = 0, status_: str = "", limit: int = 100, before: int = 0):
        where, args = ["1 = 1"], []
        if target_id:
            where.append("p.target_id = ?")
            args.append(target_id)
        if status_:
            where.append("p.status = ?")
            args.append(status_)
        if before:
            where.append("p.id < ?")
            args.append(before)
        return store.rows(
            "SELECT p.*, c.login, c.score, c.title, c.path IS NOT NULL AS has_file, t.name AS target_name, t.kind "
            f"FROM publications p JOIN clips c ON c.id = p.clip_id LEFT JOIN targets t ON t.id = p.target_id "
            f"WHERE {' AND '.join(where)} ORDER BY p.id DESC LIMIT ?", *args, min(limit, 300))

    @api.post("/api/publications/{pub_id}/retry")
    async def retry(pub_id: int):
        store.execute("UPDATE publications SET status = 'queued', error = NULL WHERE id = ? AND status = 'error'", pub_id)
        return {"ok": True}

    @api.delete("/api/publications/{pub_id}")
    async def delete_pub(pub_id: int):
        p = store.row("SELECT * FROM publications WHERE id = ?", pub_id)
        if p and p["status"] in ("queued", "error"):
            store.execute("DELETE FROM publications WHERE id = ?", pub_id)
            return {"ok": True}
        try:
            await app.publisher.delete(pub_id)
        except Exception as e:
            raise HTTPException(400, str(e)[:300])
        return {"ok": True}

    # ---- streamers ----
    @api.get("/api/streamers")
    async def streamers():
        live = {login: ch for login, ch in app.channels.items()}
        out = []
        for p in store.streamers():
            ch = live.get(p["login"])
            out.append({**p, "live": bool(ch), "viewers": ch.stream.viewers if ch else None,
                        "title": ch.stream.title if ch else None,
                        "has_preview": (app.previews / f"{p['login']}.jpg").exists()})
        known = {p["login"] for p in out}
        for login, ch in live.items():
            if login not in known:
                out.append({"login": login, "display_name": ch.stream.display_name, "avatar": ch.stream.avatar,
                            "list": "auto", "layout": "", "facecam": None, "sensitivity": 1.0, "hashtags": [],
                            "live": True, "viewers": ch.stream.viewers, "title": ch.stream.title,
                            "has_preview": (app.previews / f"{login}.jpg").exists()})
        stats = {r["login"]: r for r in store.rows(
            "SELECT login, COUNT(*) AS clips, COALESCE(SUM(status = 'published'), 0) AS published, ROUND(AVG(score), 1) AS avg_score "
            "FROM clips WHERE created_at > ? GROUP BY login", time.time() - 86400)}
        for s in out:
            s["stats"] = stats.get(s["login"], {"clips": 0, "published": 0, "avg_score": None})
        return out

    @api.put("/api/streamers/{login}")
    async def put_streamer(login: str, body: dict = Body()):
        login = login.lower().strip()
        fields = {}
        if "list" in body:
            if body["list"] not in ("white", "black", "auto"):
                raise HTTPException(400, "list: white | black | auto")
            fields["list"] = body["list"]
        if "layout" in body:
            if body["layout"] not in ("", *LAYOUTS):
                raise HTTPException(400, "неизвестная раскладка")
            fields["layout"] = body["layout"]
        if "facecam" in body:
            fc = body["facecam"]
            if fc is not None and (len(fc) != 4 or not all(0 <= float(v) <= 1 for v in fc)):
                raise HTTPException(400, "facecam: [x, y, w, h] в долях кадра")
            fields["facecam"] = [round(float(v), 4) for v in fc] if fc else None
        if "sensitivity" in body:
            fields["sensitivity"] = max(0.3, min(float(body["sensitivity"]), 3.0))
        if "hashtags" in body:
            fields["hashtags"] = [("#" + t.lstrip("#")).strip() for t in body["hashtags"] if t.strip("# ")]
        ch = app.channels.get(login)
        if ch and not store.streamer(login):
            fields.update(display_name=ch.stream.display_name, avatar=ch.stream.avatar)
        store.upsert_streamer(login, **fields)
        app.reload_profiles()
        return store.streamer(login)

    @api.delete("/api/streamers/{login}")
    async def delete_streamer(login: str):
        store.delete_streamer(login.lower())
        app.reload_profiles()
        return {"ok": True}

    # ---- settings ----
    @api.get("/api/settings")
    async def get_settings():
        return {k: mask(k, getattr(app.s, k)) for k in EDITABLE}

    @api.put("/api/settings")
    async def put_settings(values: dict = Body()):
        current = {k: getattr(app.s, k) for k in EDITABLE}
        try:
            app.apply_settings(unmask(values, current))
        except Exception as e:
            raise HTTPException(400, f"неверное значение: {e}")
        return await get_settings()

    # ---- targets ----
    def target_out(t: dict) -> dict:
        return {**t, "config": {k: mask(k, v) for k, v in (t["config"] or {}).items()}, "policy": policy.normalize(t.get("policy")),
                "default_caption": CAPTIONS[t["kind"]], "plan": app.publisher.plan(t)}

    @api.get("/api/targets")
    async def targets():
        return {"fields": FIELDS, "captions": CAPTIONS, "targets": [target_out(t) for t in store.targets()],
                "policy": {"categories": policy.CATEGORIES, "themes": policy.THEMES, "presets": policy.PRESETS}}

    def target_fields(body: dict, old: dict | None = None) -> dict:
        out = {k: body[k] for k in ("name", "mode", "daily_limit", "min_score", "min_interval_min", "caption",
                                    "quiet_from", "quiet_to") if k in body}
        if "policy" in body:
            out["policy"] = policy.normalize(body["policy"])
        if "enabled" in body:
            out["enabled"] = int(bool(body["enabled"]))
        if "config" in body:
            kind = body.get("kind") or old["kind"]
            cfg = {k: (str(body["config"].get(k)).strip() if body["config"].get(k) not in (None, "") else None)
                   for k in FIELDS[kind]}
            new_cfg = unmask(cfg, (old or {}).get("config") or {})
            out["config"] = new_cfg
            if old and new_cfg != old["config"]:
                out.update(check_ok=None, check_message=None)
        if out.get("mode") not in (None, "auto", "manual"):
            raise HTTPException(400, "mode: auto | manual")
        return out

    @api.post("/api/targets")
    async def add_target(body: dict = Body()):
        if body.get("kind") not in FIELDS:
            raise HTTPException(400, "kind: telegram | vk | youtube")
        fields = target_fields(body)
        fields.setdefault("name", body["kind"])
        tid = store.add_target(kind=body["kind"], **{**fields, "enabled": 0})
        return target_out(store.target(tid))

    async def run_check(t: dict) -> dict:
        missing = [k for k in FIELDS[t["kind"]] if k != "privacy" and not (t["config"] or {}).get(k)]
        if missing:
            res = {"ok": False, "message": "не заполнено: " + ", ".join(missing)}
        else:
            try:
                res = {"ok": True, "message": await CHECKS[t["kind"]](app.http, t["config"])}
            except Exception as e:
                res = {"ok": False, "message": str(e)[:300]}
        store.update_target(t["id"], check_ok=int(res["ok"]), check_message=res["message"], checked_at=time.time())
        return res

    @api.put("/api/targets/{target_id}")
    async def put_target(target_id: int, body: dict = Body()):
        old = store.target(target_id)
        if not old:
            raise HTTPException(404)
        fields = target_fields(body, old)
        enable = fields.pop("enabled", None)
        store.update_target(target_id, **fields)
        if enable:
            t = store.target(target_id)
            if not t["check_ok"]:
                res = await run_check(t)
                if not res["ok"]:
                    raise HTTPException(400, f"площадка не включена: {res['message']}")
        if enable is not None:
            store.update_target(target_id, enabled=enable)
        return target_out(store.target(target_id))

    @api.delete("/api/targets/{target_id}")
    async def delete_target(target_id: int):
        store.delete_target(target_id)
        return {"ok": True}

    @api.post("/api/targets/{target_id}/check")
    async def check_target(target_id: int):
        t = store.target(target_id)
        if not t:
            raise HTTPException(404)
        return await run_check(t)

    @api.post("/api/targets/{target_id}/test")
    async def test_target(target_id: int):
        t = store.target(target_id)
        if not t:
            raise HTTPException(404)
        res = await run_check(t)
        if not res["ok"]:
            return res
        try:
            return {"ok": True, "message": await TESTS[t["kind"]](app.http, t["config"])}
        except Exception as e:
            return {"ok": False, "message": str(e)[:300]}

    # ---- brain ----
    @api.get("/api/brain")
    async def brain(hours: float = 24):
        m = app.brain.metrics(hours)
        recent = store.rows(
            "SELECT v.slug, v.login, v.title, v.created, v.duration, v.views, v.clip_id, c.source, c.score, "
            "EXISTS (SELECT 1 FROM clips x WHERE x.login = v.login AND x.moment_start BETWEEN v.created - 900 AND v.created + 900) AS covered "
            "FROM viewer_clips v LEFT JOIN clips c ON c.id = v.clip_id WHERE v.created > ? ORDER BY v.views DESC LIMIT 60",
            time.time() - hours * 3600)
        r = app.brain.ranker
        model = {"active": bool(r.model), "meta": r.meta, "last_train": app.brain.last_train or store.get_settings().get("_last_train")}
        sources = store.rows("SELECT COALESCE(source, 'detector') AS source, COUNT(*) AS n, ROUND(AVG(score), 1) AS avg, "
                             "COALESCE(SUM(status = 'published'), 0) AS published FROM clips WHERE created_at > ? GROUP BY 1",
                             time.time() - hours * 3600)
        judged = store.rows("SELECT id, login, score, judge, safety, source, created_at FROM clips WHERE judge IS NOT NULL "
                            "ORDER BY id DESC LIMIT 30")
        return {**m, "model": model, "sources": sources, "judged": judged, "viewer_clips": recent, "features": store.row(
            "SELECT COUNT(*) AS n, COUNT(DISTINCT login) AS channels FROM features")}

    # ---- health / alerts / log ----
    @api.get("/api/health")
    async def health():
        return app.monitor.health()

    @api.post("/api/alerts/link")
    async def link_alerts():
        try:
            return await app.monitor.start_link()
        except Exception as e:
            raise HTTPException(400, str(e)[:300])

    @api.post("/api/alerts/test")
    async def test_alert():
        if not app.s.alerts_chat_id:
            raise HTTPException(400, "алерты не привязаны")
        await app.monitor._send("Тестовый алерт: всё работает.")
        return {"ok": True}

    @api.get("/api/log")
    async def logs(level: str = "INFO", limit: int = 400, q: str = ""):
        levels = {"INFO": 20, "WARNING": 30, "ERROR": 40}
        rows = [r for r in app.logs.records if levels.get(r["level"], 20) >= levels.get(level, 20)
                and (not q or q.lower() in r["msg"].lower())]
        return rows[-limit:][::-1]

    dist = STATIC / "dist"
    if (dist / "assets").exists():
        api.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @api.get("/{path:path}")
    async def spa(path: str):
        index = dist / "index.html" if (dist / "index.html").exists() else STATIC / "index.html"
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return api
