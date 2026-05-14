"""FastAPI application factory for ConsensusInvest."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.types import Receive, Scope, Send

from consensusinvest.agent_swarm.router import router as agent_swarm_router
from consensusinvest.entities.router import router as entities_router
from consensusinvest.evidence_store.router import router as evidence_router
from consensusinvest.runtime.env import load_local_env
from consensusinvest.runtime.wiring import build_runtime
from consensusinvest.workflow_orchestrator.router import router as workflow_router
from consensusinvest.workflow_configs.router import router as workflow_configs_router

from .common.errors import install_error_handlers
from .report_module.router import router as report_module_router


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _install_cors(app: FastAPI) -> None:
    origins = _env_list("CONSENSUSINVEST_CORS_ORIGINS")
    if not origins:
        return
    if "*" in origins:
        raise RuntimeError(
            "CONSENSUSINVEST_CORS_ORIGINS must list explicit origins; '*' is not allowed"
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def create_app() -> FastAPI:
    load_local_env()
    app = FastAPI(
        title="ConsensusInvest API",
        version="0.1.0",
        description=(
            "Evidence-driven A-share investment research system. "
            "This server currently exposes the Report Module view APIs (docs/report_module)."
        ),
    )
    app.state.runtime = build_runtime(seed_demo_data=_env_bool("CONSENSUSINVEST_SEED_DEMO_DATA"))
    install_error_handlers(app)
    _install_cors(app)
    app.include_router(workflow_router)
    app.include_router(evidence_router)
    app.include_router(entities_router)
    app.include_router(workflow_configs_router)
    app.include_router(agent_swarm_router)
    app.include_router(report_module_router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


class LazyASGIApp:
    def __init__(self, factory: Callable[[], FastAPI]) -> None:
        self._factory = factory
        self._app: FastAPI | None = None

    def _get_app(self) -> FastAPI:
        if self._app is None:
            self._app = self._factory()
        return self._app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._get_app()(scope, receive, send)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_app(), name)


app = LazyASGIApp(create_app)
