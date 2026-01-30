from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.settings import get_settings

APIFY_RUN_URL = "https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
APIFY_ACTOR_RUN_URL = "https://api.apify.com/v2/acts/{actor_id}/runs"
APIFY_RUN_STATUS_URL = "https://api.apify.com/v2/actor-runs/{run_id}"
APIFY_DATASET_ITEMS_URL = "https://api.apify.com/v2/datasets/{dataset_id}/items"


def _normalize_actor_id(actor_id: str) -> str:
    """Apify требует username~actor-name."""
    if "~" in actor_id:
        return actor_id
    if "/" in actor_id:
        return actor_id.replace("/", "~", 1)
    return actor_id


async def run_actor_get_items(actor_id: str, payload: dict[str, Any], timeout_s: int = 120) -> list[dict]:
    settings = get_settings()
    if not settings.apify_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="APIFY_TOKEN missing")

    normalized_id = _normalize_actor_id(actor_id)

    params = {"token": settings.apify_token}
    url = APIFY_RUN_URL.format(actor_id=normalized_id)

    async def _request() -> httpx.Response:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            return await client.post(url, params=params, json=payload)

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            resp = await _request()
            if resp.status_code >= 400:
                run_id = None
                err_json: dict[str, Any] | None = None
                try:
                    err_json = resp.json()
                    run_id = (
                        err_json.get("data", {}).get("id")
                        or err_json.get("id")
                        or err_json.get("error", {}).get("runId")
                    )
                except Exception:
                    err_json = None
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "error": "Apify actor failed",
                        "status": resp.status_code,
                        "body": resp.text[:400],
                        "runId": run_id,
                        "actor": normalized_id,
                        "input_keys": list(payload.keys()),
                    },
                )
            data = resp.json()
            items = data if isinstance(data, list) else data.get("items") or data.get("data") or []
            return items  # type: ignore[return-value]
        except HTTPException:
            raise
        except Exception as exc:  # httpx/network/parsing
            last_exc = exc
            await asyncio.sleep(1)
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"error": "Apify request failed", "reason": str(last_exc) if last_exc else "unknown"},
    )


async def run_actor_and_get_dataset_items(
    actor_id: str,
    payload: dict[str, Any],
    *,
    clean: bool = True,
    limit: int = 100,
    timeout_s: int = 120,
    poll_interval_s: float = 1.0,
) -> tuple[list[dict], dict]:
    """
    Запускает run актора, ждёт завершения, затем читает items из dataset.
    Возвращает (items, meta).
    """
    settings = get_settings()
    if not settings.apify_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="APIFY_TOKEN missing")

    normalized_id = _normalize_actor_id(actor_id)
    params = {"token": settings.apify_token}
    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        # стартуем run
        try:
            run_resp = await client.post(APIFY_ACTOR_RUN_URL.format(actor_id=normalized_id), params=params, json=payload)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "Apify run start failed", "reason": str(exc), "actor": normalized_id},
            ) from exc

        if run_resp.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "error": "Apify run start failed",
                    "status": run_resp.status_code,
                    "body": run_resp.text[:400],
                    "actor": normalized_id,
                    "input_keys": list(payload.keys()),
                },
            )

        run_data = run_resp.json().get("data") or {}
        run_id = run_data.get("id")
        if not run_id:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "Apify run id missing", "actor": normalized_id, "body": run_resp.text[:400]},
            )

        # poll статуса
        final_status = None
        run_error = None
        dataset_id = None
        deadline = asyncio.get_event_loop().time() + timeout_s
        while True:
            try:
                status_resp = await client.get(APIFY_RUN_STATUS_URL.format(run_id=run_id), params=params)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "error": "Apify run status failed",
                        "reason": str(exc),
                        "actor": normalized_id,
                        "runId": run_id,
                    },
                ) from exc
            if status_resp.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "error": "Apify run status failed",
                        "status": status_resp.status_code,
                        "body": status_resp.text[:400],
                        "actor": normalized_id,
                        "runId": run_id,
                    },
                )
            data = status_resp.json().get("data") or {}
            final_status = data.get("status")
            dataset_id = data.get("defaultDatasetId")
            run_error = data.get("errorMessage")
            if final_status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
                break
            if asyncio.get_event_loop().time() > deadline:
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail={
                        "error": "Apify run timed out",
                        "actor": normalized_id,
                        "runId": run_id,
                        "status": final_status,
                        "input_keys": list(payload.keys()),
                    },
                )
            await asyncio.sleep(poll_interval_s)

        if final_status != "SUCCEEDED":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "error": "Apify run failed",
                    "actor": normalized_id,
                    "runId": run_id,
                    "status": final_status,
                    "datasetId": dataset_id,
                    "errorMessage": run_error,
                    "input_keys": list(payload.keys()),
                },
            )

        if not dataset_id:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "error": "Apify dataset missing",
                    "actor": normalized_id,
                    "runId": run_id,
                    "status": final_status,
                    "input_keys": list(payload.keys()),
                },
            )

        # читаем items постранично
        items: list[dict] = []
        page_size = min(limit, 1000)
        offset = 0
        while len(items) < limit:
            try:
                ds_resp = await client.get(
                    APIFY_DATASET_ITEMS_URL.format(dataset_id=dataset_id),
                    params={
                        "token": settings.apify_token,
                        "clean": "true" if clean else "false",
                        "limit": page_size,
                        "offset": offset,
                    },
                    headers=headers,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "error": "Apify dataset fetch failed",
                        "actor": normalized_id,
                        "runId": run_id,
                        "datasetId": dataset_id,
                        "reason": str(exc),
                    },
                ) from exc
            if ds_resp.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "error": "Apify dataset fetch failed",
                        "actor": normalized_id,
                        "runId": run_id,
                        "datasetId": dataset_id,
                        "status": ds_resp.status_code,
                        "body": ds_resp.text[:400],
                    },
                )
            page_items = ds_resp.json()
            if not isinstance(page_items, list):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "error": "Invalid dataset response",
                        "actor": normalized_id,
                        "runId": run_id,
                        "datasetId": dataset_id,
                        "body": str(page_items)[:400],
                    },
                )
            items.extend(page_items)
            if len(page_items) < page_size:
                break
            offset += page_size

        items = items[:limit]
        meta = {"actorId": normalized_id, "runId": run_id, "datasetId": dataset_id, "status": final_status}
        return items, meta
