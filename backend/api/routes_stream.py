"""GET /stream/occupancy: Server-Sent Events pushing changed crowd levels every 10 s (dashboard).
Polling every 30 s remains the fallback for the low-bandwidth PWA."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.live import latest_forecast

router = APIRouter()


def _snapshot() -> dict:
    fc = latest_forecast("lstm")
    if not len(fc):
        return {}
    first = fc[fc.horizon == 1]
    return {f"{r.route_id}|{r.direction}|{r.stop_id}": [r.level, round(float(r.pred_lf), 2)] for r in first.itertuples()}


@router.get("/stream/occupancy")
async def stream(request: Request):
    async def gen():
        last: dict = {}
        while True:
            if await request.is_disconnected():
                break
            snap = await asyncio.to_thread(_snapshot)
            changed = {k: v for k, v in snap.items() if last.get(k) != v}
            if changed:
                yield f"data: {json.dumps({'changed': changed})}\n\n"
                last = snap
            else:
                yield ": keep-alive\n\n"
            await asyncio.sleep(10)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
