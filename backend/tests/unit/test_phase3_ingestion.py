"""Tests for Phase 3 ingestion durability helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config.constants import CRYPTO_CSV_TRAINING_SOURCE
from app.ml import job_store
from app.ml.crypto_csv_ingestion import CryptoCsvTrainingIngestor


class _FakeRepository:
    """Capture rows written during CSV ingestion."""

    def __init__(self) -> None:
        self.rows: list[object] = []

    async def bulk_upsert(self, rows: list[object]) -> None:
        self.rows.extend(rows)


@pytest.mark.asyncio
async def test_crypto_csv_ingestor_normalizes_symbol_and_deduplicates_rows(tmp_path: Path) -> None:
    """CSV ingestion should normalize symbols and overwrite duplicate timestamps."""

    csv_dir = tmp_path / 'crypto-history'
    csv_dir.mkdir()
    csv_path = csv_dir / 'xbtusd.csv'
    csv_path.write_text(
        '\n'.join([
            'timestamp,open,high,low,close,volume',
            '2025-12-30T00:00:00Z,90000,91000,89000,90500,1000',
            '2025-12-31T00:00:00Z,90500,91500,90000,91000,1200',
            '2025-12-31T00:00:00Z,90501,91501,90001,91001,1300',
        ]),
        encoding='utf-8',
    )

    repository = _FakeRepository()
    ingestor = CryptoCsvTrainingIngestor(repository=repository, csv_dir=csv_dir)

    summaries = await ingestor.ingest_all()

    assert len(summaries) == 1
    assert summaries[0].symbol == 'BTC/USD'
    assert summaries[0].rows_read == 2
    assert summaries[0].rows_written == 2
    assert len(repository.rows) == 2
    first_row = repository.rows[0]
    last_row = repository.rows[-1]
    assert first_row.symbol == 'BTC/USD'
    assert first_row.asset_class == 'crypto'
    assert first_row.timeframe == '1Day'
    assert first_row.source == CRYPTO_CSV_TRAINING_SOURCE
    assert last_row.close == 91001


@pytest.mark.asyncio
async def test_crypto_csv_ingestor_requires_timestamp_column(tmp_path: Path) -> None:
    """CSV ingestion should fail fast on invalid schema."""

    csv_dir = tmp_path / 'crypto-history'
    csv_dir.mkdir()
    (csv_dir / 'btcusd.csv').write_text(
        '\n'.join([
            'open,high,low,close,volume',
            '1,2,0.5,1.5,100',
        ]),
        encoding='utf-8',
    )

    ingestor = CryptoCsvTrainingIngestor(repository=_FakeRepository(), csv_dir=csv_dir)

    with pytest.raises(Exception, match='missing required columns'):
        await ingestor.ingest_all()


def test_job_store_persists_jobs_to_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Job store should keep ML job state durable across reloads."""

    runtime_dir = tmp_path / '.runtime'
    runtime_file = runtime_dir / 'ml_jobs.json'
    monkeypatch.setattr(job_store, '_RUNTIME_DIR', runtime_dir)
    monkeypatch.setattr(job_store, '_JOB_STORE_PATH', runtime_file)

    created = job_store.create_job(
        {
            'job_id': 'phase3-test-job',
            'type': 'backfill_crypto_csv',
            'asset_class': 'crypto',
            'symbols': ['BTCUSD'],
            'status': 'running',
            'started_at': datetime(2026, 4, 20, tzinfo=UTC).isoformat(),
            'finished_at': None,
            'total_symbols': 1,
            'done_symbols': 0,
            'current_symbol': None,
            'total_batches': 1,
            'done_batches': 0,
            'rows_fetched': 0,
            'progress_pct': 0,
            'error': None,
            'result': None,
        },
    )
    assert created['job_id'] == 'phase3-test-job'

    updated = job_store.update_job('phase3-test-job', current_symbol='BTC/USD', progress_pct=55)
    assert updated is not None
    assert updated['progress_pct'] == 55

    reloaded = job_store.get_job('phase3-test-job')
    assert reloaded is not None
    assert reloaded['current_symbol'] == 'BTC/USD'
    assert runtime_file.exists()
