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

    def _read_csv(
        self,
        csv_path: Path,
    ) -> tuple[str, list[CandleRow]]:

        dedup: dict[datetime, CandleRow] = {}

        with csv_path.open("r", newline="", encoding="utf-8") as handle:

            reader = csv.DictReader(handle)

            required = {
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
            }

            if not required.issubset(reader.fieldnames or set()):

                raise ResearchParseError(
                    f"{csv_path.name} missing required columns"
                )

            symbol = self._normalize_symbol(csv_path.stem)

            for row in reader:

                ts = datetime.fromisoformat(
                    row["timestamp"].replace("Z", "+00:00")
                ).astimezone(UTC)

                dedup[ts] = CandleRow(
                    symbol=symbol,
                    asset_class="crypto",
                    timeframe="1Day",
                    source=CRYPTO_CSV_TRAINING_SOURCE,
                    time=ts,
                    open=self._parse_float(
                        row["open"],
                        field_name="open",
                        file_name=csv_path.name,
                    ),
                    high=self._parse_float(
                        row["high"],
                        field_name="high",
                        file_name=csv_path.name,
                    ),
                    low=self._parse_float(
                        row["low"],
                        field_name="low",
                        file_name=csv_path.name,
                    ),
                    close=self._parse_float(
                        row["close"],
                        field_name="close",
                        file_name=csv_path.name,
                    ),
                    volume=self._parse_float(
                        row["volume"],
                        field_name="volume",
                        file_name=csv_path.name,
                    ),
                )

        return symbol, list(dedup.values())

    async def ingest_all(self) -> list[IngestSummary]:

        summaries: list[IngestSummary] = []

        for csv_file in sorted(self.csv_dir.glob("*.csv")):

            symbol, rows = self._read_csv(csv_file)

            if hasattr(self.repository, "upsert_candles"):
                await self.repository.upsert_candles(rows)
            elif hasattr(self.repository, "save_candles"):
                await self.repository.save_candles(rows)
            else:
                # fallback for test fake repo
                self.repository.rows.extend(rows)  # type: ignore[attr-defined]

            summaries.append(
                IngestSummary(
                    symbol=symbol,
                    rows_read=len(rows),
                    rows_written=len(rows),
                )
            )

        return summaries