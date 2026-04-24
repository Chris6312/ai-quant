"""Tests for Phase 3 ingestion durability helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.ml import job_store
from app.ml.crypto_csv_ingestion import CryptoCsvTrainingIngestor


class _FakeRepository:
    """Capture rows written during CSV ingestion."""

    def __init__(self) -> None:
        self.rows: list[object] = []

    async def bulk_upsert(self, rows: list[object]) -> None:
        self.rows.extend(rows)


@pytest.mark.asyncio
async def test_crypto_csv_ingestor_reads_kraken_daily_files_only_and_deduplicates_rows(
    tmp_path: Path,
) -> None:
    """CSV ingestion should read Kraken daily files and deduplicate by timestamp."""

    csv_dir = tmp_path / "crypto-history"
    csv_dir.mkdir()

    (csv_dir / "xbtusd_1440.csv").write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,vwap,volume,count",
                "1767052800,90000,91000,89000,90500,90250,1000,10",
                "1767139200,90500,91500,90000,91000,90750,1200,11",
                "1767139200,90501,91501,90001,91001,90751,1300,12",
            ]
        ),
        encoding="utf-8",
    )

    repository = _FakeRepository()
    ingestor = CryptoCsvTrainingIngestor(repository=repository, csv_dir=csv_dir)

    summaries = await ingestor.ingest_all()

    assert len(summaries) == 1
    assert summaries[0].symbol == "BTC/USD"
    assert summaries[0].rows_read == 3
    assert summaries[0].rows_written == 2

    assert len(repository.rows) == 2

    first_row = repository.rows[0]
    last_row = repository.rows[-1]

    assert first_row.symbol == "BTC/USD"
    assert first_row.asset_class == "crypto"
    assert first_row.timeframe == "1Day"
    assert first_row.source == "crypto_csv_training"
    assert first_row.time == datetime.fromtimestamp(1767052800, tz=UTC)

    assert last_row.time == datetime.fromtimestamp(1767139200, tz=UTC)
    assert last_row.close == 91001
    assert last_row.volume == 1300


@pytest.mark.asyncio
async def test_crypto_csv_ingestor_rejects_non_daily_files(tmp_path: Path) -> None:
    """CSV ingestion should fail loudly on non-daily Kraken timeframe files."""

    csv_dir = tmp_path / "crypto-history"
    csv_dir.mkdir()

    (csv_dir / "adausd_5.csv").write_text(
        "\n".join(
            [
                "1767052800,1.00,1.10,0.95,1.05,1.03,100,4",
            ]
        ),
        encoding="utf-8",
    )

    repository = _FakeRepository()
    ingestor = CryptoCsvTrainingIngestor(repository=repository, csv_dir=csv_dir)

    with pytest.raises(Exception, match="invalid_timeframe"):
        await ingestor.ingest_all()

    assert repository.rows == []


@pytest.mark.asyncio
async def test_crypto_csv_ingestor_requires_kraken_positional_columns(
    tmp_path: Path,
) -> None:
    """CSV ingestion should fail on incomplete Kraken rows."""

    csv_dir = tmp_path / "crypto-history"
    csv_dir.mkdir()

    (csv_dir / "btcusd_1440.csv").write_text(
        "\n".join(
            [
                "1,2,0.5,1.5,100",
            ]
        ),
        encoding="utf-8",
    )

    ingestor = CryptoCsvTrainingIngestor(repository=_FakeRepository(), csv_dir=csv_dir)

    with pytest.raises(Exception, match="missing_columns"):
        await ingestor.ingest_all()


@pytest.mark.asyncio
async def test_crypto_csv_ingestor_reads_headerless_seven_column_kraken_files(
    tmp_path: Path,
) -> None:
    """Kraken headerless 7-column files should use column 6 as volume."""

    csv_dir = tmp_path / "crypto-history"
    csv_dir.mkdir()

    (csv_dir / "adausd_1440.csv").write_text(
        "1767052800,0.30,0.35,0.29,0.33,9876.5,44",
        encoding="utf-8",
    )

    repository = _FakeRepository()
    ingestor = CryptoCsvTrainingIngestor(repository=repository, csv_dir=csv_dir)

    summaries = await ingestor.ingest_all()

    assert summaries[0].symbol == "ADA/USD"
    assert len(repository.rows) == 1
    first_row = repository.rows[0]
    assert first_row.volume == 9876.5
    assert first_row.usage == "ml"


@pytest.mark.asyncio
async def test_crypto_csv_ingestor_daily_import_ignores_intraday_files(
    tmp_path: Path,
) -> None:
    """Manual ML CSV import should load only Kraken 1440 files from mixed folders."""

    csv_dir = tmp_path / "crypto-history"
    csv_dir.mkdir()

    (csv_dir / "aaveusd_1.csv").write_text(
        "1767052800,300,310,290,305,100,4",
        encoding="utf-8",
    )
    (csv_dir / "aaveusd_1440.csv").write_text(
        "1767052800,300,310,290,305,100,4",
        encoding="utf-8",
    )

    repository = _FakeRepository()
    ingestor = CryptoCsvTrainingIngestor(repository=repository, csv_dir=csv_dir)

    summaries = await ingestor.ingest_daily_files()

    assert [summary.symbol for summary in summaries] == ["AAVE/USD"]
    assert len(repository.rows) == 1
    assert repository.rows[0].timeframe == "1Day"


def test_job_store_persists_jobs_to_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Job store should keep ML job state durable across reloads."""

    runtime_dir = tmp_path / ".runtime"
    runtime_file = runtime_dir / "ml_jobs.json"
    monkeypatch.setattr(job_store, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(job_store, "_JOB_STORE_PATH", runtime_file)

    created = job_store.create_job(
        {
            "job_id": "phase3-test-job",
            "type": "backfill_crypto_csv",
            "asset_class": "crypto",
            "symbols": ["BTCUSD"],
            "status": "running",
            "started_at": datetime(2026, 4, 20, tzinfo=UTC).isoformat(),
            "finished_at": None,
            "total_symbols": 1,
            "done_symbols": 0,
            "current_symbol": None,
            "total_batches": 1,
            "done_batches": 0,
            "rows_fetched": 0,
            "progress_pct": 0,
            "error": None,
            "result": None,
        },
    )
    assert created["job_id"] == "phase3-test-job"

    updated = job_store.update_job(
        "phase3-test-job",
        current_symbol="BTC/USD",
        progress_pct=55,
    )
    assert updated is not None
    assert updated["progress_pct"] == 55

    reloaded = job_store.get_job("phase3-test-job")
    assert reloaded is not None
    assert reloaded["current_symbol"] == "BTC/USD"
    assert runtime_file.exists()
