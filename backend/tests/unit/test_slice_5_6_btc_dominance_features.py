"""Slice 5.6 BTC dominance history feature tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.db.models import BitcoinDominanceDailyRow
from app.ml.btc_dominance_loader import parse_btc_dominance_csv
from app.ml.features import CRYPTO_FEATURES, FeatureEngineer, ResearchInputs
from app.ml.training_inputs import CryptoTrainingInputAssembler
from app.models.domain import Candle


def test_parse_tokeninsight_btc_dominance_csv(tmp_path: Path) -> None:
    """The TokenInsight dashboard export should parse percent strings into floats."""

    csv_path = tmp_path / "btc-d.csv"
    csv_path.write_text(
        '"Date","BTC Market Cap","ETH Market Cap"\n'
        '"2026-04-26","60.630000%","8.000000%"\n'
        '"2026-04-27","60.100000%","8.100000%"\n',
        encoding="utf-8",
    )

    rows = parse_btc_dominance_csv(csv_path)

    assert [row.dominance_date for row in rows] == [
        date(2026, 4, 26),
        date(2026, 4, 27),
    ]
    assert rows[0].dominance_pct == 60.63


def test_crypto_feature_contract_uses_compressed_btc_dominance_not_raw_timeframes() -> None:
    """Slice 5.6 adds compressed macro features, not raw lower-timeframe candles."""

    assert "btc_dominance_level" in CRYPTO_FEATURES
    assert "btc_dominance_change_1d" in CRYPTO_FEATURES
    assert "btc_dominance_change_7d" in CRYPTO_FEATURES
    assert "btc_dominance_pressure" in CRYPTO_FEATURES
    forbidden_raw_timeframe_tokens = ("5m", "15m", "1h", "4h")
    assert not any(
        token in feature_name
        for feature_name in CRYPTO_FEATURES
        for token in forbidden_raw_timeframe_tokens
    )


def test_feature_engineer_keeps_btc_dominance_features_for_crypto() -> None:
    """Crypto feature rows should carry BTC.D history features into training."""

    start = datetime(2025, 1, 1, tzinfo=UTC)
    candles = [
        Candle(
            symbol="SOL/USD",
            asset_class="crypto",
            time=start + timedelta(days=index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1_000.0 + index,
            timeframe="1Day",
            source="alpaca",
        )
        for index in range(205)
    ]

    features = FeatureEngineer().build(
        candles,
        "crypto",
        ResearchInputs(
            btc_dominance_level=60.63,
            btc_dominance_change_1d=0.25,
            btc_dominance_change_7d=1.5,
            btc_dominance_pressure=0.66,
        ),
    )

    assert features is not None
    assert features["btc_dominance_level"] == 60.63
    assert features["btc_dominance_change_1d"] == 0.25
    assert features["btc_dominance_change_7d"] == 1.5
    assert features["btc_dominance_pressure"] == 0.66


def test_btc_dominance_features_default_neutral_when_history_missing() -> None:
    """Missing BTC.D history must not drop or bias ML rows."""

    assembler = CryptoTrainingInputAssembler()
    research = assembler._with_btc_dominance_features(
        ResearchInputs(news_sentiment_1d=0.2),
        sentiment_date=date(2026, 4, 27),
        dominance_rows=[],
    )

    assert research.news_sentiment_1d == 0.2
    assert research.btc_dominance_level == 0.0
    assert research.btc_dominance_pressure == 0.0


def test_btc_dominance_features_use_latest_available_history() -> None:
    """Historical BTC.D rows should produce level, trend deltas, and pressure."""

    assembler = CryptoTrainingInputAssembler()
    rows = [
        BitcoinDominanceDailyRow(
            dominance_date=date(2026, 4, 20),
            dominance_pct=58.0,
            source="test",
            created_at=datetime(2026, 4, 20, tzinfo=UTC),
            updated_at=datetime(2026, 4, 20, tzinfo=UTC),
        ),
        BitcoinDominanceDailyRow(
            dominance_date=date(2026, 4, 26),
            dominance_pct=60.0,
            source="test",
            created_at=datetime(2026, 4, 26, tzinfo=UTC),
            updated_at=datetime(2026, 4, 26, tzinfo=UTC),
        ),
        BitcoinDominanceDailyRow(
            dominance_date=date(2026, 4, 27),
            dominance_pct=60.63,
            source="test",
            created_at=datetime(2026, 4, 27, tzinfo=UTC),
            updated_at=datetime(2026, 4, 27, tzinfo=UTC),
        ),
    ]

    research = assembler._with_btc_dominance_features(
        ResearchInputs(),
        sentiment_date=date(2026, 4, 27),
        dominance_rows=rows,
    )

    assert research.btc_dominance_level == 60.63
    assert round(research.btc_dominance_change_1d, 2) == 0.63
    assert round(research.btc_dominance_change_7d, 2) == 2.63
    assert research.btc_dominance_pressure == 0.66
