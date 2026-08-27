import re
from io import BytesIO

from reportlab.pdfgen import canvas

from firebench.metrics.table import (
    SCORECARD_COLORS,
    _fit_font_size,
    _scorecard_comparison_cell_colors,
    _scorecard_comparison_rows,
    _scorecard_group_name,
    _scorecard_kpi_name,
    _scorecard_title,
    save_comparison_as_table,
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
    assert _scorecard_kpi_name("FB001_FPH097", "Average Jaccard Index WH13") == ("Average Jaccard Index")
    assert _scorecard_kpi_name("FB001_FP02", "Average Jaccard Index W2") == ("Average Jaccard Index")


def test_scorecard_kpi_name_full_name_keeps_benchmark_id_and_full_kpi_name():
    assert (
        _scorecard_kpi_name("FB001_FPH097", "Average Jaccard Index WH13", full_name=True)
        == "FB001_FPH097: Average Jaccard Index WH13"
    )


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


def _scorecard_data(benchmarks: dict, score_card: dict) -> dict:
    return {
        "case_id": "FB001",
        "benchmark_short_name": "2021_Caldor",
        "evaluated_model_name": "test-model",
        "firebench_version": "test",
        "case_version": "test",
        "benchmarks": benchmarks,
        "score_card": score_card,
    }


def test_save_as_table_reports_group_dropped_by_aggregation(tmp_path):
    """A weather group with no eligible TSO station has no score to render."""
    data = _scorecard_data(
        {"FB001_FP01": {"Average Jaccard Index WH13": 0.5, "Score": 60.0}},
        {
            "Scheme": {
                "FP_H13": {"weight": 1, "benchmarks": {"FB001_FP01": 1}},
                "Air Temp W1": {"weight": 1, "benchmarks": {"FB001_WX001": 1, "FB001_WX004": 0}},
            },
            "Score FP_H13": 60.0,
            "Score Total": 60.0,
            "aggregation_scheme_name": "H013_P_W",
        },
    )

    output_path = tmp_path / "scorecard.pdf"
    save_as_table(output_path, data, signed=False, certificate_name="certificate_verif_lvl")

    assert output_path.exists()


def test_save_as_table_skips_ignored_kpi_inside_scored_group(tmp_path):
    """An ignored KPI keeps its group scored but produces no benchmark result to render."""
    data = _scorecard_data(
        {"FB001_WX001": {"Air temp MAE min W1 TSO": 1.5, "Score": 70.0}},
        {
            "Scheme": {
                "Air Temp W1": {"weight": 1, "benchmarks": {"FB001_WX001": 1, "FB001_WX004": 0}},
            },
            "Score Air Temp W1": 70.0,
            "Score Total": 70.0,
            "aggregation_scheme_name": "WX1",
        },
    )

    output_path = tmp_path / "scorecard.pdf"
    save_as_table(output_path, data, signed=False, certificate_name="certificate_verif_lvl")

    assert output_path.exists()


def test_save_as_table_reports_run_without_any_eligible_group(tmp_path):
    """Every weighted group was dropped, so aggregation recorded no total score."""
    data = _scorecard_data(
        {},
        {
            "Scheme": {"Air Temp W1": {"weight": 1, "benchmarks": {"FB001_WX001": 1}}},
            "aggregation_scheme_name": "WX1",
        },
    )

    output_path = tmp_path / "scorecard.pdf"
    save_as_table(output_path, data, signed=False, certificate_name="certificate_verif_lvl")

    assert output_path.exists()


def test_scorecard_comparison_rows_mark_missing_scores_as_not_scored():
    scored = _scorecard_data(
        {"FB001_WX001": {"Air temp MAE min W1 TSO": 1.5, "Score": 70.0}},
        {
            "Scheme": {"Air Temp W1": {"weight": 1, "benchmarks": {"FB001_WX001": 1}}},
            "Score Air Temp W1": 70.0,
            "Score Total": 70.0,
            "aggregation_scheme_name": "WX1",
        },
    )
    unscored = _scorecard_data(
        {},
        {
            "Scheme": {"Air Temp W1": {"weight": 1, "benchmarks": {"FB001_WX001": 1}}},
            "aggregation_scheme_name": "WX1",
        },
    )

    rows = _scorecard_comparison_rows([scored, unscored], include_kpis=True)

    assert rows[0] == ("Total Score", [70.0, None])
    assert rows[1] == ("Group: Air Temp W1", [70.0, None])
    assert rows[2] == ("Air temp MAE min W1 TSO", [70.0, None])


def test_scorecard_comparison_cell_colors_mark_missing_scores():
    colors_for_row = _scorecard_comparison_cell_colors([70.0, None])

    assert colors_for_row[1] == SCORECARD_COLORS["invalid_score"]
    assert colors_for_row[0] != colors_for_row[1]


def test_save_comparison_as_table_renders_missing_scores(tmp_path):
    scored = _scorecard_data(
        {"FB001_WX001": {"Air temp MAE min W1 TSO": 1.5, "Score": 70.0}},
        {
            "Scheme": {"Air Temp W1": {"weight": 1, "benchmarks": {"FB001_WX001": 1}}},
            "Score Air Temp W1": 70.0,
            "Score Total": 70.0,
            "aggregation_scheme_name": "WX1",
        },
    )
    unscored = _scorecard_data(
        {},
        {
            "Scheme": {"Air Temp W1": {"weight": 1, "benchmarks": {"FB001_WX001": 1}}},
            "aggregation_scheme_name": "WX1",
        },
    )

    output_path = tmp_path / "comparison.pdf"
    save_comparison_as_table(output_path, [scored, unscored], include_kpis=True)

    assert output_path.exists()


def test_scorecard_comparison_rows_include_total_and_groups():
    results = [
        {
            "case_id": "FB001",
            "evaluated_model_name": "model-a",
            "benchmarks": {
                "FB001_FPH097": {
                    "Average Jaccard Index WH13": 0.8,
                    "Score": 80.0,
                },
                "FB001_WX343": {
                    "Air temp MAE min WH13 TSO": 1.5,
                    "Score": 70.0,
                },
            },
            "score_card": {
                "Scheme": {
                    "FP_H13": {
                        "weight": 1,
                        "benchmarks": {
                            "FB001_FPH097": 1,
                        },
                    },
                    "Air Temp WH1": {
                        "weight": 1,
                        "benchmarks": {
                            "FB001_WX343": 1,
                        },
                    },
                },
                "Score Total": 80.0,
                "Score FP_H13": 90.0,
                "Score Air Temp WH1": 70.0,
                "aggregation_scheme_name": "H013_P",
                "group_display_names": {
                    "FP_H13": "Fire Perimeters",
                },
            },
        },
        {
            "case_id": "FB001",
            "evaluated_model_name": "model-b",
            "benchmarks": {
                "FB001_FPH097": {
                    "Average Jaccard Index WH13": 0.6,
                    "Score": 60.0,
                },
                "FB001_WX343": {
                    "Air temp MAE min WH13 TSO": 1.0,
                    "Score": 75.0,
                },
            },
            "score_card": {
                "Scheme": {
                    "FP_H13": {
                        "weight": 1,
                        "benchmarks": {
                            "FB001_FPH097": 1,
                        },
                    },
                    "Air Temp WH1": {
                        "weight": 1,
                        "benchmarks": {
                            "FB001_WX343": 1,
                        },
                    },
                },
                "Score Total": 60.0,
                "Score FP_H13": 50.0,
                "Score Air Temp WH1": 75.0,
                "aggregation_scheme_name": "H013_P",
            },
        },
    ]

    assert _scorecard_comparison_rows(results) == [
        ("Total Score", [80.0, 60.0]),
        ("Group: Fire Perimeters", [90.0, 50.0]),
        ("Group: Air Temp WH1", [70.0, 75.0]),
    ]
    assert _scorecard_comparison_rows(results, include_kpis=True) == [
        ("Total Score", [80.0, 60.0]),
        ("Group: Fire Perimeters", [90.0, 50.0]),
        ("Average Jaccard Index", [80.0, 60.0]),
        ("Group: Air Temp WH1", [70.0, 75.0]),
        ("Air temp MAE min WH13 TSO", [70.0, 75.0]),
    ]


def test_scorecard_comparison_cell_colors_map_absolute_scores_with_rdylgn():
    assert _scorecard_comparison_cell_colors([-10.0, 0.0, 25.0, 50.0, 75.0, 100.0, 110.0]) == [
        "#A50026",
        "#A50026",
        "#F98E52",
        "#FEFFBE",
        "#84CA66",
        "#006837",
        "#006837",
    ]


def test_fit_font_size_reduces_long_header_text_to_column_width():
    pdf_canvas = canvas.Canvas(BytesIO())
    font_size = _fit_font_size(
        pdf_canvas,
        "WRF-SFIRE legacy Rothermel Forecast",
        "Helvetica-Bold",
        max_width=105,
        max_size=8,
        min_size=4,
    )

    assert font_size < 8
    assert pdf_canvas.stringWidth("WRF-SFIRE legacy Rothermel Forecast", "Helvetica-Bold", font_size) <= 105


def test_save_comparison_as_table_creates_pdf(tmp_path):
    results = [
        {
            "case_id": "FB001",
            "benchmark_short_name": "2021_Caldor",
            "evaluated_model_name": "model-a",
            "firebench_version": "test",
            "case_version": "test",
            "score_card": {
                "Scheme": {
                    "FP_H13": {
                        "weight": 1,
                        "benchmarks": {},
                    },
                },
                "Score Total": 80.0,
                "Score FP_H13": 90.0,
                "aggregation_scheme_name": "H013_P",
            },
        },
        {
            "case_id": "FB001",
            "benchmark_short_name": "2021_Caldor",
            "evaluated_model_name": "model-b",
            "firebench_version": "test",
            "case_version": "test",
            "score_card": {
                "Scheme": {
                    "FP_H13": {
                        "weight": 1,
                        "benchmarks": {},
                    },
                },
                "Score Total": 60.0,
                "Score FP_H13": 50.0,
                "aggregation_scheme_name": "H013_P",
            },
        },
    ]

    output_path = tmp_path / "comparison.pdf"
    save_comparison_as_table(output_path, results)

    assert output_path.exists()
    assert output_path.read_bytes().startswith(b"%PDF")
