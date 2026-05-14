import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from consensusinvest.agent_swarm import (
    InMemoryAgentSwarmRepository,
    LiteLLMAgentProvider,
    SQLiteAgentSwarmRepository,
    build_agent_llm_provider_from_env,
)
from consensusinvest.entities import InMemoryEntityRepository, SQLiteEntityRepository
from consensusinvest.evidence_store import InMemoryEvidenceStoreClient, SQLiteEvidenceStoreClient
from consensusinvest.app import create_app
from consensusinvest.report_module.repository import SQLiteReportRunRepository
from consensusinvest.runtime.env import load_local_env
from consensusinvest.runtime.repository import SQLiteRuntimeEventRepository
from consensusinvest.runtime.wiring import build_evidence_store_from_env, build_runtime
from consensusinvest.search_agent import SQLiteSearchTaskRepository
from consensusinvest.workflow_orchestrator import (
    InMemoryWorkflowRepository,
    SQLiteWorkflowRepository,
)


def test_load_local_env_reads_utf8_values_without_overriding_existing_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# local config",
                "TAVILY_API_KEY=from_file",
                "EXA_API_KEY='exa_密钥'",
                "CONSENSUSINVEST_HOST=0.0.0.0 # local bind",
                'CONSENSUSINVEST_EXA_SEARCH_TYPE="auto"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TAVILY_API_KEY", "from_process")
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.delenv("CONSENSUSINVEST_HOST", raising=False)
    monkeypatch.delenv("CONSENSUSINVEST_EXA_SEARCH_TYPE", raising=False)

    loaded = load_local_env(env_file)

    assert os.environ["TAVILY_API_KEY"] == "from_process"
    assert os.environ["EXA_API_KEY"] == "exa_密钥"
    assert os.environ["CONSENSUSINVEST_HOST"] == "0.0.0.0"
    assert os.environ["CONSENSUSINVEST_EXA_SEARCH_TYPE"] == "auto"
    assert loaded == {
        "EXA_API_KEY": "exa_密钥",
        "CONSENSUSINVEST_HOST": "0.0.0.0",
        "CONSENSUSINVEST_EXA_SEARCH_TYPE": "auto",
    }


def test_load_local_env_can_override_existing_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("TAVILY_API_KEY=from_file\n", encoding="utf-8")
    monkeypatch.setenv("TAVILY_API_KEY", "from_process")

    loaded = load_local_env(env_file, override=True)

    assert os.environ["TAVILY_API_KEY"] == "from_file"
    assert loaded == {"TAVILY_API_KEY": "from_file"}


def test_load_local_env_rejects_invalid_lines(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TAVILY_API_KEY\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing '='"):
        load_local_env(env_file)


def test_agent_llm_provider_env_factory(monkeypatch):
    monkeypatch.delenv("CONSENSUSINVEST_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("CONSENSUSINVEST_LLM_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="CONSENSUSINVEST_LLM_PROVIDER is required"):
        build_agent_llm_provider_from_env()

    monkeypatch.setenv("CONSENSUSINVEST_LLM_PROVIDER", "local")
    with pytest.raises(RuntimeError, match="unsupported CONSENSUSINVEST_LLM_PROVIDER"):
        build_agent_llm_provider_from_env()

    monkeypatch.setenv("CONSENSUSINVEST_LLM_PROVIDER", "litellm")
    monkeypatch.setenv("CONSENSUSINVEST_LLM_MODEL", "openai/gpt-4.1-mini")
    monkeypatch.setenv("CONSENSUSINVEST_SWARM_MODEL", "openai/gpt-4.1")
    monkeypatch.setenv("CONSENSUSINVEST_JUDGE_MODEL", "openai/gpt-4.1")
    monkeypatch.setenv("CONSENSUSINVEST_LLM_TEMPERATURE", "0.1")
    provider = build_agent_llm_provider_from_env()

    assert isinstance(provider, LiteLLMAgentProvider)
    assert provider.model == "openai/gpt-4.1-mini"
    assert provider.model_for("agent_argument") == "openai/gpt-4.1"
    assert provider.model_for("judge") == "openai/gpt-4.1"
    assert provider.temperature == 0.1


def test_evidence_store_env_factory_requires_sqlite_path(monkeypatch):
    monkeypatch.setenv("CONSENSUSINVEST_EVIDENCE_STORE_BACKEND", "sqlite")
    monkeypatch.delenv("CONSENSUSINVEST_EVIDENCE_DB_PATH", raising=False)

    with pytest.raises(RuntimeError, match="CONSENSUSINVEST_EVIDENCE_DB_PATH is required"):
        build_evidence_store_from_env()


def test_evidence_store_env_factory_builds_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "evidence.sqlite3"
    monkeypatch.setenv("CONSENSUSINVEST_EVIDENCE_STORE_BACKEND", "sqlite")
    monkeypatch.setenv("CONSENSUSINVEST_EVIDENCE_DB_PATH", str(db_path))

    store = build_evidence_store_from_env()

    assert isinstance(store, SQLiteEvidenceStoreClient)
    store.close()


def test_evidence_store_env_factory_memory_requires_explicit_allow(monkeypatch):
    monkeypatch.setenv("CONSENSUSINVEST_EVIDENCE_STORE_BACKEND", "memory")
    monkeypatch.delenv("CONSENSUSINVEST_ALLOW_IN_MEMORY_RUNTIME", raising=False)

    with pytest.raises(RuntimeError, match="CONSENSUSINVEST_ALLOW_IN_MEMORY_RUNTIME"):
        build_evidence_store_from_env()

    monkeypatch.setenv("CONSENSUSINVEST_ALLOW_IN_MEMORY_RUNTIME", "1")
    assert isinstance(build_evidence_store_from_env(), InMemoryEvidenceStoreClient)


def test_build_runtime_does_not_seed_demo_data_by_default(monkeypatch):
    monkeypatch.setenv("CONSENSUSINVEST_LLM_PROVIDER", "litellm")
    monkeypatch.setenv("CONSENSUSINVEST_LLM_MODEL", "openai/gpt-4.1-mini")
    monkeypatch.setenv("CONSENSUSINVEST_EVIDENCE_STORE_BACKEND", "memory")
    monkeypatch.setenv("CONSENSUSINVEST_ALLOW_IN_MEMORY_RUNTIME", "1")

    runtime = build_runtime()

    rows, total = runtime.entity_repository.list_entities(limit=100, offset=0)
    assert rows == []
    assert total == 0


def test_build_runtime_uses_sqlite_state_repositories_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSENSUSINVEST_LLM_PROVIDER", "litellm")
    monkeypatch.setenv("CONSENSUSINVEST_LLM_MODEL", "openai/gpt-4.1-mini")
    monkeypatch.setenv("CONSENSUSINVEST_EVIDENCE_STORE_BACKEND", "sqlite")
    monkeypatch.setenv("CONSENSUSINVEST_EVIDENCE_DB_PATH", str(tmp_path / "evidence.sqlite3"))
    monkeypatch.setenv("CONSENSUSINVEST_RUNTIME_DB_PATH", str(tmp_path / "runtime.sqlite3"))
    monkeypatch.delenv("CONSENSUSINVEST_ALLOW_IN_MEMORY_RUNTIME", raising=False)

    runtime = build_runtime()

    assert isinstance(runtime.entity_repository, SQLiteEntityRepository)
    assert isinstance(runtime.agent_repository, SQLiteAgentSwarmRepository)
    assert isinstance(runtime.workflow_repository, SQLiteWorkflowRepository)
    assert isinstance(runtime.report_repository, SQLiteReportRunRepository)
    assert isinstance(runtime.runtime_event_repository, SQLiteRuntimeEventRepository)
    assert isinstance(runtime.search_pool.repository, SQLiteSearchTaskRepository)
    search_db_rows = runtime.search_pool.repository._connection.execute(
        "PRAGMA database_list"
    ).fetchall()
    search_db_path = next(row["file"] for row in search_db_rows if row["name"] == "main")
    assert Path(search_db_path) == tmp_path / "runtime.search_agent.sqlite3"
    runtime_event_db_rows = runtime.runtime_event_repository._connection.execute(
        "PRAGMA database_list"
    ).fetchall()
    runtime_event_db_path = next(row["file"] for row in runtime_event_db_rows if row["name"] == "main")
    assert Path(runtime_event_db_path) == tmp_path / "runtime.runtime_events.sqlite3"
    assert runtime.agent_repository.new_judgment_id() == "jdg_000001"
    assert (
        runtime.report_repository.new_report_run_id(
            "000001",
            created_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        )
        == "rpt_20260514_000001_0001"
    )
    runtime.evidence_store.close()
    runtime.search_pool.repository.close()
    runtime.agent_repository.close()
    runtime.workflow_repository.close()
    runtime.report_repository.close()
    runtime.runtime_event_repository.close()


def test_build_runtime_keeps_explicit_in_memory_escape_hatch(monkeypatch):
    monkeypatch.setenv("CONSENSUSINVEST_LLM_PROVIDER", "litellm")
    monkeypatch.setenv("CONSENSUSINVEST_LLM_MODEL", "openai/gpt-4.1-mini")
    monkeypatch.setenv("CONSENSUSINVEST_EVIDENCE_STORE_BACKEND", "memory")
    monkeypatch.setenv("CONSENSUSINVEST_ALLOW_IN_MEMORY_RUNTIME", "1")

    runtime = build_runtime()

    assert isinstance(runtime.evidence_store, InMemoryEvidenceStoreClient)
    assert isinstance(runtime.entity_repository, InMemoryEntityRepository)
    assert isinstance(runtime.agent_repository, InMemoryAgentSwarmRepository)
    assert isinstance(runtime.workflow_repository, InMemoryWorkflowRepository)
    assert runtime.report_repository is None
    assert runtime.runtime_event_repository is None
    search_db_rows = runtime.search_pool.repository._connection.execute("PRAGMA database_list").fetchall()
    search_db_path = next(row["file"] for row in search_db_rows if row["name"] == "main")
    assert search_db_path in {"", ":memory:"}
    runtime.search_pool.repository.close()


def test_importing_app_module_does_not_build_runtime(monkeypatch):
    monkeypatch.delenv("CONSENSUSINVEST_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("CONSENSUSINVEST_LLM_MODEL", raising=False)

    from consensusinvest import app as app_module

    assert app_module.app._app is None


def test_create_app_installs_explicit_cors_origins(monkeypatch):
    monkeypatch.setenv("CONSENSUSINVEST_LLM_PROVIDER", "litellm")
    monkeypatch.setenv("CONSENSUSINVEST_LLM_MODEL", "openai/gpt-4.1-mini")
    monkeypatch.setenv("CONSENSUSINVEST_EVIDENCE_STORE_BACKEND", "memory")
    monkeypatch.setenv("CONSENSUSINVEST_ALLOW_IN_MEMORY_RUNTIME", "1")
    monkeypatch.setenv(
        "CONSENSUSINVEST_CORS_ORIGINS",
        "http://localhost:5173, http://127.0.0.1:5173",
    )

    app = create_app()

    cors = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )
    assert cors.kwargs["allow_origins"] == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    assert cors.kwargs["allow_credentials"] is True


def test_create_app_rejects_wildcard_cors_with_credentials(monkeypatch):
    monkeypatch.setenv("CONSENSUSINVEST_LLM_PROVIDER", "litellm")
    monkeypatch.setenv("CONSENSUSINVEST_LLM_MODEL", "openai/gpt-4.1-mini")
    monkeypatch.setenv("CONSENSUSINVEST_EVIDENCE_STORE_BACKEND", "memory")
    monkeypatch.setenv("CONSENSUSINVEST_ALLOW_IN_MEMORY_RUNTIME", "1")
    monkeypatch.setenv("CONSENSUSINVEST_CORS_ORIGINS", "*")

    with pytest.raises(RuntimeError, match="explicit origins"):
        create_app()
