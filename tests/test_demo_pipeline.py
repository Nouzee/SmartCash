import csv

from smart_money.demo import run_demo


def test_demo_keeps_realtime_features_and_future_labels_separate(tmp_path) -> None:
    manifest = run_demo(tmp_path, duration_seconds=420, seed=11)

    feature_path = tmp_path / "feature_snapshots.csv"
    label_path = tmp_path / "markout_labels.csv"
    summary_path = tmp_path / "backtest_summary.csv"
    assert feature_path.is_file() and label_path.is_file() and summary_path.is_file()
    with feature_path.open(newline="", encoding="utf-8") as handle:
        feature_columns = next(csv.reader(handle))
    with label_path.open(newline="", encoding="utf-8") as handle:
        label_columns = next(csv.reader(handle))

    assert not any("markout" in column or column.startswith("future_") for column in feature_columns)
    assert "uses_future_data" in feature_columns
    assert "signed_markout" in label_columns
    assert manifest["dataset_mode"] == "synthetic_demo"
    assert manifest["empirical_claims_allowed"] is False
    assert manifest["feature_rows"] > 0
    assert manifest["label_rows"] > 0
