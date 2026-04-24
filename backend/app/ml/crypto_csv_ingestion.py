from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config.constants import CRYPTO_CSV_TRAINING_SOURCE, ML_CANDLE_USAGE
from app.db.models import CandleRow
from app.exceptions import ResearchParseError
from app.repositories.candles import CandleRepository

_DAILY_KRAKEN_INTERVAL = "1440"
_HEADER_TOKENS = {"date", "time", "timestamp", "unix", "open_time"}


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
                f"invalid_csv_format: invalid {field_name} value "
                f"'{raw_value}' in {file_name}"
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
                f"invalid_csv_format: invalid timestamp value "
                f"'{raw_value}' in {file_name}"
            ) from exc

        return datetime.fromtimestamp(unix_seconds, tz=UTC)

    def _filename_parts(self, csv_path: Path) -> tuple[str, str]:
        stem = csv_path.stem
        symbol_stem, separator, interval = stem.rpartition("_")
        if separator == "" or not interval.isdigit():
            raise ResearchParseError(
                f"invalid_timeframe: {csv_path.name} must use Kraken naming "
                "<SYMBOL>_<INTERVAL>.csv"
            )
        return symbol_stem, interval

    def _symbol_from_filename(self, csv_path: Path) -> str:
        symbol_stem, _ = self._filename_parts(csv_path)
        return self._normalize_symbol(symbol_stem)

    def _ensure_daily_file(self, csv_path: Path) -> None:
        _, interval = self._filename_parts(csv_path)
        if interval != _DAILY_KRAKEN_INTERVAL:
            raise ResearchParseError(
                f"invalid_timeframe: {csv_path.name} has Kraken interval "
                f"{interval}; expected {_DAILY_KRAKEN_INTERVAL} for 1D ML candles"
            )

    def _is_header_row(self, row: list[str]) -> bool:
        first_cell = row[0].strip().lower()
        return first_cell in _HEADER_TOKENS

    def _volume_index(self, row: list[str], *, file_name: str, line_number: int) -> int:
        if len(row) == 7:
            return 5
        if len(row) >= 8:
            return 6
        raise ResearchParseError(
            f"missing_columns: {file_name} row {line_number} has fewer than 7 columns"
        )

    def _read_csv(self, csv_path: Path) -> tuple[str, list[CandleRow], int]:
        self._ensure_daily_file(csv_path)

        dedup: dict[datetime, CandleRow] = {}
        rows_seen = 0

        with csv_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            symbol = self._symbol_from_filename(csv_path)

            for line_number, row in enumerate(reader, start=1):
                if not row or not any(cell.strip() for cell in row):
                    continue
                if self._is_header_row(row):
                    continue

                volume_index = self._volume_index(
                    row,
                    file_name=csv_path.name,
                    line_number=line_number,
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
                        row[volume_index],
                        field_name="volume",
                        file_name=csv_path.name,
                    ),
                    usage=ML_CANDLE_USAGE,
                )

        return symbol, list(dedup.values()), rows_seen

    async def ingest_files(self, csv_files: Sequence[Path]) -> list[IngestSummary]:
        summaries: list[IngestSummary] = []

        for csv_file in csv_files:
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

    async def ingest_daily_files(self) -> list[IngestSummary]:
        """Ingest only Kraken daily 1D files and ignore intraday files in the folder."""

        return await self.ingest_files(sorted(self.csv_dir.glob("*_1440.csv")))

    async def ingest_all(self) -> list[IngestSummary]:
        """Ingest every CSV file, preserving strict timeframe validation for tests/tools."""

        return await self.ingest_files(sorted(self.csv_dir.glob("*.csv")))
