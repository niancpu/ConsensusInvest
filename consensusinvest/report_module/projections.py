"""Pure projection helpers for Report Module views."""

from __future__ import annotations

from typing import Any

from consensusinvest.entities.repository import EntityRecord
from consensusinvest.evidence_store.models import MarketSnapshot

from .schemas import IndexIntradayPoint
from ._utils import _dt

def _stock_code(entity: EntityRecord) -> str | None:
    for value in entity.aliases:
        text = value.strip().upper()
        if "." in text and text.split(".", 1)[0].isdigit():
            return text
    return None

def _ticker(entity: EntityRecord) -> str | None:
    stock_code = _stock_code(entity)
    if stock_code:
        return stock_code.split(".", 1)[0]
    for value in entity.aliases:
        text = value.strip()
        if text.isdigit():
            return text
    return None

def _exchange(stock_code: str | None) -> str:
    if not stock_code or "." not in stock_code:
        return ""
    return stock_code.rsplit(".", 1)[1]

def _action_label(signal: str) -> str:
    return {"positive": "看多", "neutral": "观望", "negative": "看空"}.get(signal, signal)

def _snapshot_matches_keyword(snapshot: MarketSnapshot, keyword: str | None) -> bool:
    if not keyword or not keyword.strip():
        return True
    needle = keyword.strip().lower()
    values = [
        snapshot.ticker or "",
        str(snapshot.metrics.get("stock_code") or ""),
        str(snapshot.metrics.get("ticker") or ""),
        str(snapshot.metrics.get("name") or ""),
    ]
    return any(needle in value.lower() for value in values)

def _normalize_index_code(code: str) -> str:
    text = code.strip().upper()
    if text in {"000001", "SH000001"}:
        return "000001.SH"
    if text in {"399001", "SZ399001"}:
        return "399001.SZ"
    if text in {"399006", "SZ399006"}:
        return "399006.SZ"
    if "." in text:
        left, right = text.split(".", 1)
        return f"{left}.{right}"
    suffix = "SH" if text.startswith(("0", "5", "6", "9")) else "SZ"
    return f"{text}.{suffix}"

def _index_ticker(code: str) -> str:
    return code.split(".", 1)[0]

def _index_name(code: str) -> str:
    return {
        "000001.SH": "上证指数",
        "399001.SZ": "深证成指",
        "399006.SZ": "创业板指",
    }.get(code, code)

def _index_intraday_snapshots(
    reader: ReportRuntimeReader,
    normalized_code: str,
    ticker: str,
) -> list[MarketSnapshot]:
    snapshots = reader.market_snapshots_for_ticker(ticker, ("index_quote",), limit=500)
    return [
        snapshot
        for snapshot in snapshots
        if _normalize_index_code(str(snapshot.metrics.get("code") or snapshot.ticker or "")) == normalized_code
    ]

def _intraday_points_from_snapshots(snapshots: list[MarketSnapshot]) -> list[IndexIntradayPoint]:
    if not snapshots:
        return []
    latest = snapshots[0]
    raw_points = latest.metrics.get("intraday_points")
    if isinstance(raw_points, list) and raw_points:
        points = [_intraday_point_from_mapping(item, latest) for item in raw_points if isinstance(item, dict)]
        return [point for point in points if point is not None]

    points: list[IndexIntradayPoint] = []
    for snapshot in reversed(snapshots):
        value = _float_or_none(snapshot.metrics.get("value") or snapshot.metrics.get("close") or snapshot.metrics.get("price"))
        if value is None:
            continue
        timestamp = _dt(snapshot.snapshot_time)
        points.append(
            IndexIntradayPoint(
                time=_point_time(timestamp),
                timestamp=timestamp,
                value=value,
                change=_float_or_none(snapshot.metrics.get("change")),
                change_rate=_float_or_none(snapshot.metrics.get("change_rate")),
                volume=_float_or_none(snapshot.metrics.get("volume")),
                amount=_float_or_none(snapshot.metrics.get("amount")),
            )
        )
    return points

def _intraday_point_from_mapping(item: dict[str, Any], snapshot: MarketSnapshot) -> IndexIntradayPoint | None:
    value = _float_or_none(item.get("value") or item.get("close") or item.get("price"))
    if value is None:
        return None
    timestamp = str(item.get("timestamp") or item.get("datetime") or item.get("time") or _dt(snapshot.snapshot_time))
    return IndexIntradayPoint(
        time=str(item.get("time") or _point_time(timestamp)),
        timestamp=timestamp,
        value=value,
        change=_float_or_none(item.get("change")),
        change_rate=_float_or_none(item.get("change_rate")),
        volume=_float_or_none(item.get("volume")),
        amount=_float_or_none(item.get("amount")),
    )

def _point_time(timestamp: str) -> str:
    if "T" in timestamp:
        return timestamp.split("T", 1)[1][:5]
    if " " in timestamp:
        return timestamp.split(" ", 1)[1][:5]
    return timestamp[:5]

def _trade_date(points: list[IndexIntradayPoint], snapshot: MarketSnapshot | None) -> str:
    if points:
        timestamp = points[-1].timestamp
        if "T" in timestamp:
            return timestamp.split("T", 1)[0]
        if " " in timestamp:
            return timestamp.split(" ", 1)[0]
    if snapshot and snapshot.snapshot_time is not None:
        return snapshot.snapshot_time.date().isoformat()
    return ""

def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _trend(value: object) -> str:
    text = str(value or "flat")
    return text if text in {"warming", "cooling", "flat"} else "flat"

def _string_list(value: object) -> list[str]:
    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    return []
