from __future__ import annotations

from pathlib import Path

from app.ml.model_registry import _fold_with_loaded_importances


def test_fold_importance_hydration_replaces_stale_registry_metadata(
    tmp_path: Path,
) -> None:
    """Rejected fold diagnostics should prefer richer artifact feature metadata."""

    artifact = tmp_path / "model_crypto_fold139.lgbm"
    artifact.write_text(
        "\n".join(
            [
                "feature_names=news_sentiment_1d btc_dominance_level btc_dominance_pressure",
                "Tree=0",
                "split_feature=0 1 2",
                "split_gain=1 2 3",
            ]
        ),
        encoding="utf-8",
    )
    fold = {
        "fold_index": 139,
        "train_start": "2025-01-01T00:00:00+00:00",
        "train_end": "2025-06-01T00:00:00+00:00",
        "test_start": "2025-06-02T00:00:00+00:00",
        "test_end": "2025-07-01T00:00:00+00:00",
        "validation_sharpe": 2.64,
        "validation_accuracy": 0.175,
        "n_train_samples": 100,
        "n_test_samples": 20,
        "model_path": str(artifact),
        "feature_names": ["news_sentiment_1d"],
        "feature_importances": {"news_sentiment_1d": 1.0},
        "class_balance": {},
        "eligibility_status": "research_only",
        "eligibility_reason": "test",
    }

    hydrated = _fold_with_loaded_importances(fold)

    assert hydrated["feature_names"] == [
        "news_sentiment_1d",
        "btc_dominance_level",
        "btc_dominance_pressure",
    ]
    assert set(hydrated["feature_importances"]) == {
        "news_sentiment_1d",
        "btc_dominance_level",
        "btc_dominance_pressure",
    }
