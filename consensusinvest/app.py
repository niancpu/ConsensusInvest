"""FastAPI application factory for ConsensusInvest."""

from __future__ import annotations

from fastapi import FastAPI

from consensusinvest.agent_swarm.router import router as agent_swarm_router
from consensusinvest.entities.router import router as entities_router
from consensusinvest.evidence_store.router import router as evidence_router
from consensusinvest.runtime.wiring import build_runtime
from consensusinvest.workflow_orchestrator.router import router as workflow_router
from consensusinvest.workflow_configs.router import router as workflow_configs_router

from .common.errors import install_error_handlers
from .report_module.router import router as report_module_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="ConsensusInvest API",
        version="0.1.0",
        description=(
            "Evidence-driven A-share investment research system. "
            "This server currently exposes the Report Module view APIs (docs/report_module)."
        ),
    )
    app.state.runtime = build_runtime(seed_demo_data=True)
    install_error_handlers(app)
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


app = create_app()
