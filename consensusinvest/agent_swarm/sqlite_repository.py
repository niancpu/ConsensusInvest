"""SQLite-backed Agent Swarm repository."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from consensusinvest.evidence_store import EvidenceReference

from .models import (
    AgentArgumentDraft,
    AgentArgumentRecord,
    AgentRunRecord,
    JudgeToolCallRecord,
    JudgmentRecord,
    RoundSummaryDraft,
    RoundSummaryRecord,
)


class SQLiteAgentSwarmRepository:
    """Persistent Agent Swarm and Judge Runtime projection repository."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self._conn.close()

    def start_agent_run(
        self,
        *,
        workflow_run_id: str,
        agent_id: str,
        role: str,
        started_at: datetime,
    ) -> AgentRunRecord:
        run = AgentRunRecord(
            agent_run_id=self._next_id("arun"),
            workflow_run_id=workflow_run_id,
            agent_id=agent_id,
            role=role,
            status="running",
            started_at=started_at,
        )
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO agent_runs (
                    agent_run_id, workflow_run_id, agent_id, role, status,
                    started_at, completed_at, rounds_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.agent_run_id,
                    run.workflow_run_id,
                    run.agent_id,
                    run.role,
                    run.status,
                    _dt_dump(run.started_at),
                    _dt_dump(run.completed_at),
                    _json_dump(list(run.rounds)),
                ),
            )
        return run

    def complete_agent_run(
        self,
        agent_run_id: str,
        *,
        completed_at: datetime,
        rounds: tuple[int, ...],
    ) -> AgentRunRecord:
        current = self._load_agent_run(agent_run_id)
        if current is None:
            raise KeyError(agent_run_id)
        updated = AgentRunRecord(
            agent_run_id=current.agent_run_id,
            workflow_run_id=current.workflow_run_id,
            agent_id=current.agent_id,
            role=current.role,
            status="completed",
            started_at=current.started_at,
            completed_at=completed_at,
            rounds=rounds,
        )
        with self._conn:
            self._conn.execute(
                """
                UPDATE agent_runs
                SET status = ?, completed_at = ?, rounds_json = ?
                WHERE agent_run_id = ?
                """,
                (
                    updated.status,
                    _dt_dump(updated.completed_at),
                    _json_dump(list(updated.rounds)),
                    updated.agent_run_id,
                ),
            )
        return updated

    def save_argument(
        self,
        *,
        workflow_run_id: str,
        agent_run_id: str,
        draft: AgentArgumentDraft,
        created_at: datetime,
    ) -> AgentArgumentRecord:
        argument = AgentArgumentRecord(
            agent_argument_id=self._next_id("arg"),
            agent_run_id=agent_run_id,
            workflow_run_id=workflow_run_id,
            agent_id=draft.agent_id,
            role=draft.role,
            round=draft.round,
            argument=draft.argument,
            confidence=draft.confidence,
            referenced_evidence_ids=draft.referenced_evidence_ids,
            counter_evidence_ids=draft.counter_evidence_ids,
            limitations=draft.limitations,
            role_output=dict(draft.role_output),
            created_at=created_at,
        )
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO agent_arguments (
                    agent_argument_id, agent_run_id, workflow_run_id, agent_id,
                    role, round, argument, confidence, referenced_evidence_ids_json,
                    counter_evidence_ids_json, limitations_json, role_output_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    argument.agent_argument_id,
                    argument.agent_run_id,
                    argument.workflow_run_id,
                    argument.agent_id,
                    argument.role,
                    argument.round,
                    argument.argument,
                    argument.confidence,
                    _json_dump(list(argument.referenced_evidence_ids)),
                    _json_dump(list(argument.counter_evidence_ids)),
                    _json_dump(list(argument.limitations)),
                    _json_dump(argument.role_output),
                    _dt_dump(argument.created_at),
                ),
            )
        return argument

    def save_round_summary(
        self,
        draft: RoundSummaryDraft,
        *,
        created_at: datetime,
    ) -> RoundSummaryRecord:
        summary = RoundSummaryRecord(
            workflow_run_id=draft.workflow_run_id,
            round=draft.round,
            summary=draft.summary,
            participants=draft.participants,
            agent_argument_ids=draft.agent_argument_ids,
            referenced_evidence_ids=draft.referenced_evidence_ids,
            disputed_evidence_ids=draft.disputed_evidence_ids,
            round_summary_id=self._next_id("rsum"),
            created_at=created_at,
        )
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO round_summaries (
                    round_summary_id, workflow_run_id, round, summary,
                    participants_json, agent_argument_ids_json,
                    referenced_evidence_ids_json, disputed_evidence_ids_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.round_summary_id,
                    summary.workflow_run_id,
                    summary.round,
                    summary.summary,
                    _json_dump(list(summary.participants)),
                    _json_dump(list(summary.agent_argument_ids)),
                    _json_dump(list(summary.referenced_evidence_ids)),
                    _json_dump(list(summary.disputed_evidence_ids)),
                    _dt_dump(summary.created_at),
                ),
            )
        return summary

    def save_judgment(self, judgment: JudgmentRecord) -> JudgmentRecord:
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO judgments (
                    judgment_id, workflow_run_id, final_signal, confidence,
                    time_horizon, key_positive_evidence_ids_json,
                    key_negative_evidence_ids_json, reasoning, risk_notes_json,
                    suggested_next_checks_json, referenced_agent_argument_ids_json,
                    limitations_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    judgment.judgment_id,
                    judgment.workflow_run_id,
                    judgment.final_signal,
                    judgment.confidence,
                    judgment.time_horizon,
                    _json_dump(list(judgment.key_positive_evidence_ids)),
                    _json_dump(list(judgment.key_negative_evidence_ids)),
                    judgment.reasoning,
                    _json_dump(list(judgment.risk_notes)),
                    _json_dump(list(judgment.suggested_next_checks)),
                    _json_dump(list(judgment.referenced_agent_argument_ids)),
                    _json_dump(list(judgment.limitations)),
                    _dt_dump(judgment.created_at),
                ),
            )
        return judgment

    def new_judgment_id(self) -> str:
        return self._next_id("jdg")

    def save_tool_call(self, call: JudgeToolCallRecord) -> JudgeToolCallRecord:
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO judge_tool_calls (
                    tool_call_id, judgment_id, tool_name, input_json,
                    result_ref_json, output_summary, referenced_evidence_ids_json,
                    used_for, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    call.tool_call_id,
                    call.judgment_id,
                    call.tool_name,
                    _json_dump(call.input),
                    _json_dump(call.result_ref),
                    call.output_summary,
                    _json_dump(list(call.referenced_evidence_ids)),
                    call.used_for,
                    _dt_dump(call.created_at),
                ),
            )
        return call

    def new_tool_call_id(self) -> str:
        return self._next_id("jtc")

    def save_references(self, references: list[EvidenceReference]) -> None:
        with self._conn:
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO agent_evidence_references (
                    reference_id, source_type, source_id, evidence_id,
                    reference_role, round, workflow_run_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        ref.reference_id,
                        ref.source_type,
                        ref.source_id,
                        ref.evidence_id,
                        ref.reference_role,
                        ref.round,
                        ref.workflow_run_id,
                        _dt_dump(ref.created_at),
                    )
                    for ref in references
                ],
            )

    def list_agent_runs(self, workflow_run_id: str) -> list[AgentRunRecord]:
        return [
            _agent_run_from_row(row)
            for row in self._conn.execute(
                """
                SELECT * FROM agent_runs
                WHERE workflow_run_id = ?
                ORDER BY rowid ASC
                """,
                (workflow_run_id,),
            ).fetchall()
        ]

    def list_arguments(
        self,
        workflow_run_id: str,
        *,
        agent_id: str | None = None,
        round: int | None = None,
    ) -> list[AgentArgumentRecord]:
        conditions = ["workflow_run_id = ?"]
        params: list[Any] = [workflow_run_id]
        if agent_id is not None:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if round is not None:
            conditions.append("round = ?")
            params.append(round)
        rows = self._conn.execute(
            f"""
            SELECT * FROM agent_arguments
            WHERE {' AND '.join(conditions)}
            ORDER BY rowid ASC
            """,
            params,
        ).fetchall()
        return [_argument_from_row(row) for row in rows]

    def get_argument(self, agent_argument_id: str) -> AgentArgumentRecord | None:
        row = self._conn.execute(
            "SELECT * FROM agent_arguments WHERE agent_argument_id = ?",
            (agent_argument_id,),
        ).fetchone()
        return _argument_from_row(row) if row is not None else None

    def list_round_summaries(self, workflow_run_id: str) -> list[RoundSummaryRecord]:
        return [
            _round_summary_from_row(row)
            for row in self._conn.execute(
                """
                SELECT * FROM round_summaries
                WHERE workflow_run_id = ?
                ORDER BY rowid ASC
                """,
                (workflow_run_id,),
            ).fetchall()
        ]

    def get_round_summary(self, round_summary_id: str) -> RoundSummaryRecord | None:
        row = self._conn.execute(
            "SELECT * FROM round_summaries WHERE round_summary_id = ?",
            (round_summary_id,),
        ).fetchone()
        return _round_summary_from_row(row) if row is not None else None

    def get_judgment(self, judgment_id: str) -> JudgmentRecord | None:
        row = self._conn.execute(
            "SELECT * FROM judgments WHERE judgment_id = ?",
            (judgment_id,),
        ).fetchone()
        return _judgment_from_row(row) if row is not None else None

    def get_judgment_by_workflow(self, workflow_run_id: str) -> JudgmentRecord | None:
        row = self._conn.execute(
            """
            SELECT * FROM judgments
            WHERE workflow_run_id = ?
            ORDER BY rowid ASC
            LIMIT 1
            """,
            (workflow_run_id,),
        ).fetchone()
        return _judgment_from_row(row) if row is not None else None

    def list_tool_calls(self, judgment_id: str) -> list[JudgeToolCallRecord]:
        return [
            _tool_call_from_row(row)
            for row in self._conn.execute(
                """
                SELECT * FROM judge_tool_calls
                WHERE judgment_id = ?
                ORDER BY rowid ASC
                """,
                (judgment_id,),
            ).fetchall()
        ]

    def list_references(
        self,
        *,
        source_type: str | None = None,
        source_id: str | None = None,
        workflow_run_id: str | None = None,
    ) -> list[EvidenceReference]:
        conditions: list[str] = []
        params: list[Any] = []
        if source_type is not None:
            conditions.append("source_type = ?")
            params.append(source_type)
        if source_id is not None:
            conditions.append("source_id = ?")
            params.append(source_id)
        if workflow_run_id is not None:
            conditions.append("workflow_run_id = ?")
            params.append(workflow_run_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._conn.execute(
            f"""
            SELECT * FROM agent_evidence_references
            {where}
            ORDER BY rowid ASC
            """,
            params,
        ).fetchall()
        return [_reference_from_row(row) for row in rows]

    def _ensure_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS id_sequences (
                    prefix TEXT PRIMARY KEY,
                    next_value INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_runs (
                    agent_run_id TEXT PRIMARY KEY,
                    workflow_run_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    rounds_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_arguments (
                    agent_argument_id TEXT PRIMARY KEY,
                    agent_run_id TEXT NOT NULL,
                    workflow_run_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    round INTEGER NOT NULL,
                    argument TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    referenced_evidence_ids_json TEXT NOT NULL,
                    counter_evidence_ids_json TEXT NOT NULL,
                    limitations_json TEXT NOT NULL,
                    role_output_json TEXT NOT NULL,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS round_summaries (
                    round_summary_id TEXT PRIMARY KEY,
                    workflow_run_id TEXT NOT NULL,
                    round INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    participants_json TEXT NOT NULL,
                    agent_argument_ids_json TEXT NOT NULL,
                    referenced_evidence_ids_json TEXT NOT NULL,
                    disputed_evidence_ids_json TEXT NOT NULL,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS judgments (
                    judgment_id TEXT PRIMARY KEY,
                    workflow_run_id TEXT NOT NULL,
                    final_signal TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    time_horizon TEXT NOT NULL,
                    key_positive_evidence_ids_json TEXT NOT NULL,
                    key_negative_evidence_ids_json TEXT NOT NULL,
                    reasoning TEXT NOT NULL,
                    risk_notes_json TEXT NOT NULL,
                    suggested_next_checks_json TEXT NOT NULL,
                    referenced_agent_argument_ids_json TEXT NOT NULL,
                    limitations_json TEXT NOT NULL,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS judge_tool_calls (
                    tool_call_id TEXT PRIMARY KEY,
                    judgment_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    result_ref_json TEXT NOT NULL,
                    output_summary TEXT NOT NULL,
                    referenced_evidence_ids_json TEXT NOT NULL,
                    used_for TEXT,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS agent_evidence_references (
                    reference_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    reference_role TEXT NOT NULL,
                    round INTEGER,
                    workflow_run_id TEXT,
                    created_at TEXT
                );
                """
            )
            self._conn.execute(
                """
                INSERT INTO metadata (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO NOTHING
                """,
                ("schema_version", "1"),
            )

    def _next_id(self, prefix: str) -> str:
        if prefix not in {"arun", "arg", "rsum", "jdg", "jtc"}:
            raise ValueError(f"unknown id prefix: {prefix}")
        with self._conn:
            row = self._conn.execute(
                "SELECT next_value FROM id_sequences WHERE prefix = ?",
                (prefix,),
            ).fetchone()
            current = int(row["next_value"]) if row is not None else 1
            self._conn.execute(
                """
                INSERT INTO id_sequences (prefix, next_value) VALUES (?, ?)
                ON CONFLICT(prefix) DO UPDATE SET next_value = excluded.next_value
                """,
                (prefix, current + 1),
            )
        return f"{prefix}_{current:06d}"

    def _load_agent_run(self, agent_run_id: str) -> AgentRunRecord | None:
        row = self._conn.execute(
            "SELECT * FROM agent_runs WHERE agent_run_id = ?",
            (agent_run_id,),
        ).fetchone()
        return _agent_run_from_row(row) if row is not None else None


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)


def _dt_dump(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _dt_load(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _agent_run_from_row(row: sqlite3.Row) -> AgentRunRecord:
    return AgentRunRecord(
        agent_run_id=row["agent_run_id"],
        workflow_run_id=row["workflow_run_id"],
        agent_id=row["agent_id"],
        role=row["role"],
        status=row["status"],
        started_at=_dt_load(row["started_at"]) or datetime.min,
        completed_at=_dt_load(row["completed_at"]),
        rounds=tuple(_json_load(row["rounds_json"], [])),
    )


def _argument_from_row(row: sqlite3.Row) -> AgentArgumentRecord:
    return AgentArgumentRecord(
        agent_argument_id=row["agent_argument_id"],
        agent_run_id=row["agent_run_id"],
        workflow_run_id=row["workflow_run_id"],
        agent_id=row["agent_id"],
        role=row["role"],
        round=row["round"],
        argument=row["argument"],
        confidence=row["confidence"],
        referenced_evidence_ids=tuple(_json_load(row["referenced_evidence_ids_json"], [])),
        counter_evidence_ids=tuple(_json_load(row["counter_evidence_ids_json"], [])),
        limitations=tuple(_json_load(row["limitations_json"], [])),
        role_output=dict(_json_load(row["role_output_json"], {})),
        created_at=_dt_load(row["created_at"]),
    )


def _round_summary_from_row(row: sqlite3.Row) -> RoundSummaryRecord:
    return RoundSummaryRecord(
        round_summary_id=row["round_summary_id"],
        workflow_run_id=row["workflow_run_id"],
        round=row["round"],
        summary=row["summary"],
        participants=tuple(_json_load(row["participants_json"], [])),
        agent_argument_ids=tuple(_json_load(row["agent_argument_ids_json"], [])),
        referenced_evidence_ids=tuple(_json_load(row["referenced_evidence_ids_json"], [])),
        disputed_evidence_ids=tuple(_json_load(row["disputed_evidence_ids_json"], [])),
        created_at=_dt_load(row["created_at"]),
    )


def _judgment_from_row(row: sqlite3.Row) -> JudgmentRecord:
    return JudgmentRecord(
        judgment_id=row["judgment_id"],
        workflow_run_id=row["workflow_run_id"],
        final_signal=row["final_signal"],
        confidence=row["confidence"],
        time_horizon=row["time_horizon"],
        key_positive_evidence_ids=tuple(_json_load(row["key_positive_evidence_ids_json"], [])),
        key_negative_evidence_ids=tuple(_json_load(row["key_negative_evidence_ids_json"], [])),
        reasoning=row["reasoning"],
        risk_notes=tuple(_json_load(row["risk_notes_json"], [])),
        suggested_next_checks=tuple(_json_load(row["suggested_next_checks_json"], [])),
        referenced_agent_argument_ids=tuple(_json_load(row["referenced_agent_argument_ids_json"], [])),
        limitations=tuple(_json_load(row["limitations_json"], [])),
        created_at=_dt_load(row["created_at"]),
    )


def _tool_call_from_row(row: sqlite3.Row) -> JudgeToolCallRecord:
    return JudgeToolCallRecord(
        tool_call_id=row["tool_call_id"],
        judgment_id=row["judgment_id"],
        tool_name=row["tool_name"],
        input=dict(_json_load(row["input_json"], {})),
        result_ref=dict(_json_load(row["result_ref_json"], {})),
        output_summary=row["output_summary"],
        referenced_evidence_ids=tuple(_json_load(row["referenced_evidence_ids_json"], [])),
        used_for=row["used_for"],
        created_at=_dt_load(row["created_at"]),
    )


def _reference_from_row(row: sqlite3.Row) -> EvidenceReference:
    return EvidenceReference(
        reference_id=row["reference_id"],
        source_type=row["source_type"],
        source_id=row["source_id"],
        evidence_id=row["evidence_id"],
        reference_role=row["reference_role"],
        round=row["round"],
        workflow_run_id=row["workflow_run_id"],
        created_at=_dt_load(row["created_at"]),
    )


__all__ = ["SQLiteAgentSwarmRepository"]
