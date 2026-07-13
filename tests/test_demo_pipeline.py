import csv

from smartcash.demo import run_demo


def test_demo_keeps_realtime_features_and_future_labels_separate(tmp_path) -> None:
    manifest = run_demo(tmp_path, duration_seconds=420, seed=11)

    feature_path = tmp_path / "feature_snapshots.csv"
    label_path = tmp_path / "markout_labels.csv"
    summary_path = tmp_path / "backtest_summary.csv"
    shock_event_path = tmp_path / "shock_events.csv"
    shock_outcome_path = tmp_path / "shock_outcomes.csv"
    assert all(path.is_file() for path in (feature_path, label_path, summary_path, shock_event_path, shock_outcome_path))
    with feature_path.open(newline="", encoding="utf-8") as handle:
        feature_columns = next(csv.reader(handle))
    with label_path.open(newline="", encoding="utf-8") as handle:
        label_columns = next(csv.reader(handle))

    assert not any("markout" in column or column.startswith("future_") for column in feature_columns)
    assert "uses_future_data" in feature_columns
    assert "complete_60s" in feature_columns and "complete_300s" in feature_columns
    assert "signed_markout" in label_columns
    assert manifest["dataset_mode"] == "synthetic_demo"
    assert manifest["empirical_claims_allowed"] is False
    assert manifest["feature_rows"] > 0
    assert manifest["label_rows"] > 0
    assert manifest["shock_events"] > 0
    assert manifest["shock_outcomes"] > 0
