"""FastAPI scaffolding shared by the apps: run endpoints, event stream, static UI."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .runner import Runner
from .store import Store

KIT_WEB = Path(__file__).parent / "web"


def make_app(title: str, web_dir: str | Path, store: Store, runner: Runner) -> FastAPI:
    app = FastAPI(title=title, docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.middleware("http")
    async def no_cache(request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("Cache-Control", "no-cache")
        return resp

    @app.get("/api/runs")
    def list_runs(kind: str | None = None, limit: int = 40):
        runs = store.list_runs(kind, limit)
        for r in runs:
            r.pop("output", None)
        return runs

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: int):
        run = store.get_run(run_id)
        if not run:
            raise HTTPException(404, "run not found")
        run["events"] = store.events(run_id)
        return run

    @app.get("/api/runs/{run_id}/events")
    def run_events(run_id: int, after: int = 0):
        if not store.get_run(run_id):
            raise HTTPException(404, "run not found")
        return StreamingResponse(runner.sse(run_id, after), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    def finish() -> FastAPI:
        """Mount the UI last so API routes registered by the app win."""
        web = Path(web_dir)

        @app.get("/")
        def index():
            return FileResponse(web / "index.html", headers={"Cache-Control": "no-store"})

        app.mount("/kit", StaticFiles(directory=KIT_WEB), name="kit")
        app.mount("/", StaticFiles(directory=web), name="web")
        return app

    app.finish = finish  # type: ignore[attr-defined]
    return app
