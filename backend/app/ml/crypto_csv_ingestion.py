from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config.constants import CRYPTO_CSV_TRAINING_SOURCE
from app.db.models import CandleRow
from app.exceptions import ResearchParseError
from app.repositories.candles import CandleRepository


@dataclass(slots=True)
class IngestSummary:
    symbol: str
    rows_read: int
    rows_written: int


class CryptoCsvTrainingIngestor:
    def __init__(
        self,
        repository: CandleRepository,
        csv_dir: Path,
    ) -> None:
        self.repository = repository
        self.csv_dir = csv_dir

    def _normalize_symbol(self, raw: str) -> str:
        symbol = raw.upper()

        if symbol.startswith("XBT"):
            symbol = symbol.replace("XBT", "BTC", 1)

        if "/" in symbol:
            return symbol

        if symbol.endswith("USD") and len(symbol) > 3:
            base = symbol[:-3]
            quote = symbol[-3:]
            return f"{base}/{quote}"

        return symbol

    def _parse_float(
        self,
        raw_value: str,
        *,
        field_name: str,
        file_name: str,
    ) -> float:
        try:
            return float(raw_value.strip())
        except ValueError as exc:
            raise ResearchParseError(
                f"invalid {field_name} value '{raw_value}' in {file_name}"
            ) from exc

    def _parse_timestamp(
        self,
        raw_value: str,
        *,
        file_name: str,
    ) -> datetime:
        try:
            unix_seconds = int(raw_value.strip())
        except ValueError as exc:
            raise ResearchParseError(
                f"invalid timestamp value '{raw_value}' in {file_name}"
            ) from exc

        return datetime.fromtimestamp(unix_seconds, tz=UTC)

    def _symbol_from_filename(self, csv_path: Path) -> str:
        stem = csv_path.stem
        if stem.endswith("_1440"):
            stem = stem[:-5]
        return self._normalize_symbol(stem)

    def _read_csv(self, csv_path: Path) -> tuple[str, list[CandleRow], int]:
        dedup: dict[datetime, CandleRow] = {}
        rows_seen = 0

        with csv_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            symbol = self._symbol_from_filename(csv_path)

            for line_number, row in enumerate(reader, start=1):
                if not row or not any(cell.strip() for cell in row):
                    continue

                if len(row) < 7:
                    raise ResearchParseError(
                        f"{csv_path.name} row {line_number} has fewer than 7 columns"
                    )

                timestamp = self._parse_timestamp(row[0], file_name=csv_path.name)
                rows_seen += 1
                dedup[timestamp] = CandleRow(
                    symbol=symbol,
                    asset_class="crypto",
                    timeframe="1Day",
                    source=CRYPTO_CSV_TRAINING_SOURCE,
                    time=timestamp,
                    open=self._parse_float(
                        row[1],
                        field_name="open",
                        file_name=csv_path.name,
                    ),
                    high=self._parse_float(
                        row[2],
                        field_name="high",
                        file_name=csv_path.name,
                    ),
                    low=self._parse_float(
                        row[3],
                        field_name="low",
                        file_name=csv_path.name,
                    ),
                    close=self._parse_float(
                        row[4],
                        field_name="close",
                        file_name=csv_path.name,
                    ),
                    volume=self._parse_float(
                        row[6],
                        field_name="volume",
                        file_name=csv_path.name,
                    ),
                )

        return symbol, list(dedup.values()), rows_seen

    async def ingest_all(self) -> list[IngestSummary]:
        summaries: list[IngestSummary] = []

        for csv_file in sorted(self.csv_dir.glob("*_1440.csv")):
            symbol, rows, rows_seen = self._read_csv(csv_file)

            if hasattr(self.repository, "bulk_upsert"):
                await self.repository.bulk_upsert(rows)
            elif hasattr(self.repository, "upsert_candles"):
                await self.repository.upsert_candles(rows)
            elif hasattr(self.repository, "save_candles"):
                await self.repository.save_candles(rows)
            else:
                # fallback for test fake repo
                self.repository.rows.extend(rows)  # type: ignore[attr-defined]

            summaries.append(
                IngestSummary(
                    symbol=symbol,
                    rows_read=rows_seen,
                    rows_written=len(rows),
                )
            )

        return summaries