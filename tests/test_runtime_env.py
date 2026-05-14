import os

import pytest

from consensusinvest.agent_swarm import LiteLLMAgentProvider, build_agent_llm_provider_from_env
from consensusinvest.runtime.env import load_local_env


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
    assert build_agent_llm_provider_from_env() is None

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
