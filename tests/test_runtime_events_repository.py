from datetime import datetime, timezone

from consensusinvest.runtime import RuntimeEvent, SQLiteRuntimeEventRepository


def _event(
    *,
    event_id: str = "",
    event_type: str = "agent.argument_saved",
    correlation_id: str = "corr_001",
    workflow_run_id: str | None = "wr_001",
    producer: str = "agent_swarm",
    payload: dict | None = None,
) -> RuntimeEvent:
    return RuntimeEvent(
        event_id=event_id,
        event_type=event_type,
        occurred_at=datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc),
        correlation_id=correlation_id,
        workflow_run_id=workflow_run_id,
        producer=producer,
        payload=dict(payload or {"source_id": "arg_001"}),
    )


def test_sqlite_runtime_event_repository_generates_ids_and_preserves_explicit_ids(tmp_path):
    repository = SQLiteRuntimeEventRepository(tmp_path / "runtime_events.sqlite3")

    first = repository.append_event(_event())
    explicit = repository.append_event(_event(event_id="evt_external_001"))
    second = repository.append_event(_event(event_type="judge.completed"))

    assert first.event_id == "rtevt_000001"
    assert explicit.event_id == "evt_external_001"
    assert second.event_id == "rtevt_000002"
    assert [event.event_id for event in repository.list_events()] == [
        "rtevt_000001",
        "evt_external_001",
        "rtevt_000002",
    ]
    repository.close()


def test_sqlite_runtime_event_repository_reopens_and_filters(tmp_path):
    db_path = tmp_path / "runtime_events.sqlite3"
    repository = SQLiteRuntimeEventRepository(db_path)
    repository.append_event(
        _event(
            event_type="agent.argument_saved",
            correlation_id="corr_a",
            workflow_run_id="wr_a",
            producer="agent_swarm",
            payload={"agent_argument_id": "arg_001"},
        )
    )
    repository.append_event(
        _event(
            event_type="judge.tool_called",
            correlation_id="corr_a",
            workflow_run_id="wr_a",
            producer="judge_runtime",
            payload={"tool_call_id": "jtc_001"},
        )
    )
    repository.append_event(
        _event(
            event_type="report.view_built",
            correlation_id="corr_b",
            workflow_run_id=None,
            producer="report_module",
            payload={"report_run_id": "rpt_001"},
        )
    )
    repository.close()

    reopened = SQLiteRuntimeEventRepository(db_path)

    all_events = reopened.list_events()
    assert [event.event_id for event in all_events] == [
        "rtevt_000001",
        "rtevt_000002",
        "rtevt_000003",
    ]
    assert all_events[0].payload == {"agent_argument_id": "arg_001"}
    assert all_events[2].workflow_run_id is None
    assert [
        event.event_type for event in reopened.list_events(workflow_run_id="wr_a")
    ] == ["agent.argument_saved", "judge.tool_called"]
    assert [
        event.event_type for event in reopened.list_events(correlation_id="corr_b")
    ] == ["report.view_built"]
    assert [
        event.event_type for event in reopened.list_events(producer="judge_runtime")
    ] == ["judge.tool_called"]
    assert [
        event.event_type
        for event in reopened.list_events(correlation_id="corr_a", producer="agent_swarm")
    ] == ["agent.argument_saved"]
    assert [
        event.event_id for event in reopened.list_events(limit=1, offset=1)
    ] == ["rtevt_000002"]
    reopened.close()
