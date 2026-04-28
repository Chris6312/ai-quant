"""Load daily Bitcoin dominance CSV history into the ML feature store."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BitcoinDominanceDailyRow

BTC_DOMINANCE_SOURCE = "tokeninsight_dashboard_csv"


@dataclass(frozen=True, slots=True)
class BitcoinDominanceCsvRow:
    """Normalized daily BTC dominance CSV row."""

    dominance_date: date
    dominance_pct: float


@dataclass(frozen=True, slots=True)
class BitcoinDominanceImportResult:
    """Summary of a BTC dominance CSV import."""

    source_path: str
    row_count: int
    start_date: date | None
    end_date: date | None


def parse_btc_dominance_csv(path: Path) -> list[BitcoinDominanceCsvRow]:
    """Parse TokenInsight-style BTC dominance CSV data."""

    rows: list[BitcoinDominanceCsvRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw_row in reader:
            raw_date = (raw_row.get("Date") or "").strip()
            raw_dominance = (raw_row.get("BTC Market Cap") or "").strip()
            if not raw_date or not raw_dominance:
                continue
            rows.append(
                BitcoinDominanceCsvRow(
                    dominance_date=date.fromisoformat(raw_date),
                    dominance_pct=_parse_percentage(raw_dominance),
                )
            )
    rows.sort(key=lambda row: row.dominance_date)
    return rows


async def import_btc_dominance_csv(
    session: AsyncSession,
    path: Path,
    *,
    source: str = BTC_DOMINANCE_SOURCE,
) -> BitcoinDominanceImportResult:
    """Upsert BTC dominance CSV rows into btc_dominance_daily."""

    parsed_rows = parse_btc_dominance_csv(path)
    now = datetime.now(tz=UTC)
    for parsed_row in parsed_rows:
        row = await session.get(BitcoinDominanceDailyRow, parsed_row.dominance_date)
        if row is None:
            session.add(
                BitcoinDominanceDailyRow(
                    dominance_date=parsed_row.dominance_date,
                    dominance_pct=parsed_row.dominance_pct,
                    source=source,
                    created_at=now,
                    updated_at=now,
                )
            )
            continue
        row.dominance_pct = parsed_row.dominance_pct
        row.source = source
        row.updated_at = now
    await session.commit()
    return BitcoinDominanceImportResult(
        source_path=str(path),
        row_count=len(parsed_rows),
        start_date=parsed_rows[0].dominance_date if parsed_rows else None,
        end_date=parsed_rows[-1].dominance_date if parsed_rows else None,
    )


def _parse_percentage(raw_value: str) -> float:
    stripped = raw_value.strip().removesuffix("%").strip()
    return float(stripped)
