from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Body, Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app import analyzer
from app.config import Settings, load_settings
from app.db import Database
from app.flags import extract_flags
from app.forcead import ForceADClient
from app.workers import poller_loop, submitter_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

settings = load_settings()
db = Database(settings.database_path)
forcead = ForceADClient(settings.forcead_base_url, settings.forcead_team_token)
templates = Jinja2Templates(directory="templates")


class FlagSubmitRequest(BaseModel):
    flags: list[str] | None = None
    text: str | None = None
    source: str = "api"


def check_api_token(x_app_token: Annotated[str | None, Header()] = None) -> None:
    if settings.app_token and x_app_token != settings.app_token:
        raise HTTPException(status_code=401, detail="Invalid X-App-Token")


def add_flags(text: str, source: str) -> dict[str, int | list[str]]:
    flags = extract_flags(text)
    result = db.add_flags(flags, source)
    return {**result, "total": len(flags), "flags": flags}


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    tasks = [
        asyncio.create_task(
            submitter_loop(
                db=db,
                client=forcead,
                batch_size=settings.submit_batch_size,
                interval=settings.submit_interval_seconds,
            )
        ),
        asyncio.create_task(poller_loop(db=db, client=forcead, interval=settings.poll_interval_seconds)),
    ]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="ForceAD Team Warboard", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    summary = analyzer.get_summary(db)
    attack = analyzer.get_attack_recommendations(db, settings.our_team_id)
    defense = analyzer.get_defense_recommendations(db, settings.our_team_id)
    recent_flags = analyzer.get_recent_flags(db)
    matrix = analyzer.get_service_matrix(db)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "settings": settings,
            "summary": summary,
            "attack": attack,
            "defense": defense,
            "recent_flags": recent_flags,
            "matrix": matrix,
            "status_names": analyzer.STATUS_NAMES,
        },
    )


@app.post("/submit")
async def submit_form(flags_text: Annotated[str, Form()], source: Annotated[str, Form()] = "web"):
    add_flags(flags_text, source)
    return RedirectResponse("/", status_code=303)


@app.post("/api/flags", dependencies=[Depends(check_api_token)])
async def submit_flags(payload: FlagSubmitRequest):
    text_parts = []
    if payload.text:
        text_parts.append(payload.text)
    if payload.flags:
        text_parts.extend(payload.flags)
    if not text_parts:
        raise HTTPException(status_code=400, detail="Provide flags or text")
    return add_flags("\n".join(text_parts), payload.source)


@app.post("/api/flags/text", dependencies=[Depends(check_api_token)])
async def submit_flags_text(text: Annotated[str, Body(media_type="text/plain")], source: str = "api-text"):
    return add_flags(text, source)


@app.get("/api/stats", dependencies=[Depends(check_api_token)])
async def stats():
    return analyzer.get_summary(db)


@app.get("/api/board/recommendations", dependencies=[Depends(check_api_token)])
async def recommendations():
    return {
        "attack": [dict(row) for row in analyzer.get_attack_recommendations(db, settings.our_team_id)],
        "defense": [dict(row) for row in analyzer.get_defense_recommendations(db, settings.our_team_id)],
    }


@app.get("/api/board/services", dependencies=[Depends(check_api_token)])
async def services():
    return [dict(row) for row in analyzer.get_service_matrix(db)]


@app.get("/api/flags", dependencies=[Depends(check_api_token)])
async def flags():
    return [dict(row) for row in analyzer.get_recent_flags(db, limit=200)]
