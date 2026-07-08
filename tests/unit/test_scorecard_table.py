import re

from firebench.metrics.table import (
    _scorecard_group_name,
    _scorecard_kpi_name,
    _scorecard_title,
    save_as_table,
)


def test_scorecard_title_uses_benchmark_short_name_without_agg_label():
    data = {
        "benchmark_short_name": "2021_Caldor",
        "case_id": "FB001",
        "evaluated_model_name": "test-model",
    }

    assert _scorecard_title(data, "H013_P", "VL0", "60.27") == [
        "Total Score 2021_Caldor H013_P for test-model",
        "",
        "VL0",
        "60.27",
    ]


def test_scorecard_group_name_uses_display_name_mapping():
    data = {
        "score_card": {
            "group_display_names": {
                "FP_H13": "Fire Perimeters",
            }
        }
    }

    assert _scorecard_group_name(data, "FP_H13") == "Fire Perimeters"
    assert _scorecard_group_name(data, "Air Temp WH1") == "Air Temp WH1"


def test_scorecard_kpi_name_defaults_to_short_label():
    assert _scorecard_kpi_name("FB001_FPH097", "Average Jaccard Index WH13") == (
        "Average Jaccard Index"
    )
    assert _scorecard_kpi_name("FB001_FP02", "Average Jaccard Index W2") == (
        "Average Jaccard Index"
    )


def test_scorecard_kpi_name_full_name_keeps_benchmark_id_and_full_kpi_name():
    assert _scorecard_kpi_name(
        "FB001_FPH097", "Average Jaccard Index WH13", full_name=True
    ) == "FB001_FPH097: Average Jaccard Index WH13"


def test_save_as_table_paginates_large_scorecard(tmp_path):
    n_benchmarks = 180
    benchmarks = {
        f"FB001_WX{i:03d}": {f"Weather KPI WH{i}": float(i), "Score": float(i % 100)}
        for i in range(1, n_benchmarks + 1)
    }
    scheme = {
        "Air Temp WH1": {
            "weight": 1,
            "benchmarks": {benchmark_id: 1 for benchmark_id in benchmarks},
        }
    }
    data = {
        "case_id": "FB001",
        "evaluated_model_name": "test-model",
        "firebench_version": "test",
        "case_version": "test",
        "benchmarks": benchmarks,
        "score_card": {
            "Scheme": scheme,
            "Score Air Temp WH1": 50.0,
            "Score Total": 50.0,
            "aggregation_scheme_name": "WX_WH1",
        },
    }

    output_path = tmp_path / "scorecard.pdf"
    save_as_table(output_path, data, signed=False, certificate_name="certificate_verif_lvl")

    pdf_bytes = output_path.read_bytes()
    page_objects = re.findall(rb"/Type\s*/Page\b", pdf_bytes)
    assert output_path.exists()
    assert len(page_objects) > 1
