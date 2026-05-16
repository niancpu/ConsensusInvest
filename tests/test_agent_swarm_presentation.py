from datetime import datetime, timezone

from consensusinvest.agent_swarm.models import AgentArgumentRecord, RoundSummaryRecord
from consensusinvest.agent_swarm.presentation import (
    display_agent_argument_text,
    display_judgment_reasoning,
    repair_mojibake_text,
)
from consensusinvest.agent_swarm.router import _argument_view, _round_summary_view


def test_mojibake_text_can_be_repaired_when_bytes_are_complete() -> None:
    assert repair_mojibake_text("ä¸­å›½é“¶è¡Œ") == "中国银行"


def test_agent_argument_display_falls_back_for_english_mojibake_text() -> None:
    text = display_agent_argument_text(
        argument=(
            "æåé¶è¡ exhibits signs of fundamental improvement through sustained "
            "high dividend commitment."
        ),
        agent_id="bull_v1",
        role="bullish_interpreter",
        round_number=1,
        confidence=0.65,
        referenced_evidence_ids=("ev_000022", "ev_000026"),
        counter_evidence_ids=("ev_000023",),
    )

    assert "第 1 轮多头解释代理论证" in text
    assert "ev_000022、ev_000026" in text
    assert "exhibits signs" not in text
    assert "æ" not in text


def test_agent_argument_api_projection_sanitizes_legacy_english_fields() -> None:
    row = AgentArgumentRecord(
        agent_argument_id="arg_000001",
        agent_run_id="arun_000001",
        workflow_run_id="wr_000001",
        agent_id="bull_v1",
        role="bullish_interpreter",
        round=1,
        argument="LLM argument grounded in allowed Evidence only.",
        confidence=0.65,
        referenced_evidence_ids=("ev_000022",),
        counter_evidence_ids=("ev_000023",),
        limitations=("Missing full peer comparison and valuation sensitivity.",),
        role_output={"stance_interpretation": "LLM stance", "impact": 0.57},
        created_at=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
    )

    view = _argument_view(row)

    assert "第 1 轮多头解释代理论证" in view.argument
    assert "LLM argument" not in view.argument
    assert view.limitations == ["原始局限说明不是合规中文，需补充同业对比、估值敏感性和最新经营指标验证。"]
    assert view.role_output == {"impact": 0.57}


def test_round_summary_api_projection_sanitizes_legacy_english_summary() -> None:
    row = RoundSummaryRecord(
        round_summary_id="rsum_000001",
        workflow_run_id="wr_000001",
        round=1,
        summary="LLM round summary without new facts.",
        participants=("bull_v1",),
        agent_argument_ids=("arg_000001",),
        referenced_evidence_ids=("ev_000022",),
        disputed_evidence_ids=("ev_000023",),
        created_at=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
    )

    view = _round_summary_view(row)

    assert "第 1 轮辩论摘要" in view.summary
    assert "LLM round summary" not in view.summary


def test_judgment_display_falls_back_for_generic_or_mojibake_reasoning() -> None:
    text = display_judgment_reasoning(
        reasoning="基于已保存智能体论证和关键证据形成判断。",
        final_signal="neutral",
        confidence=0.52,
        positive_evidence_ids=("ev_000022",),
        negative_evidence_ids=("ev_000023",),
        referenced_agent_argument_ids=("arg_000001",),
    )

    assert "最终判断为中性，置信度 0.52" in text
    assert "arg_000001" in text
    assert "ev_000022" in text
    assert "基于已保存智能体论证和关键证据形成判断" not in text


def test_judgment_display_falls_back_for_mojibake_reasoning() -> None:
    text = display_judgment_reasoning(
        reasoning="0.52 / ç□æ□□ï¼□1-4å□ï¼□",
        final_signal="neutral",
        confidence=0.52,
        positive_evidence_ids=("ev_000022",),
        negative_evidence_ids=("ev_000023",),
        referenced_agent_argument_ids=("arg_000001",),
    )

    assert "最终判断为中性，置信度 0.52" in text
    assert "ç" not in text
