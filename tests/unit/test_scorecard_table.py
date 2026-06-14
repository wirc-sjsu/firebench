import re

from firebench.metrics.table import save_as_table


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
