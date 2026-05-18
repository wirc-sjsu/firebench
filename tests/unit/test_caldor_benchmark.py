from pathlib import Path

from firebench.benchmarks import caldor


def test_build_registries_is_fresh():
    caldor.build_registries()
    first_r08_count = len(caldor.REQUIREMENTS["R08"]["benchmarks"])
    first_benchmark_count = len(caldor.BENCHMARK_FUNCTIONS)

    caldor.build_registries()

    assert len(caldor.REQUIREMENTS["R08"]["benchmarks"]) == first_r08_count
    assert len(caldor.BENCHMARK_FUNCTIONS) == first_benchmark_count
    assert first_r08_count == 72


def test_get_list_benchmark_with_aggregation_scheme():
    caldor.build_registries()

    assert caldor.get_list_benchmark_with_agg(caldor.AGGREGATION, "B") == [
        "FB001_BD01",
        "FB001_BD02",
        "FB001_BD03",
        "FB001_BD04",
        "FB001_BD05",
        "FB001_BD06",
    ]
    assert set(caldor.get_list_benchmark_with_agg(caldor.AGGREGATION, "0")) == set(
        caldor.BENCHMARK_FUNCTIONS
    )


def test_overwrite_previous_run(monkeypatch, tmp_path):
    output_path = tmp_path / "Caldor_rslt.json"

    assert caldor.overwrite_previous_run(False, output_path) is True

    output_path.write_text("{}")
    assert caldor.overwrite_previous_run(True, output_path) is True

    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert caldor.overwrite_previous_run(False, output_path) is False

    monkeypatch.setattr("builtins.input", lambda _: "yes")
    assert caldor.overwrite_previous_run(False, output_path) is True


def test_resolve_h5_relative_path(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    class FakeH5File:
        filename = str(data_dir / "Caldor.h5")

    assert (
        caldor.resolve_h5_relative_path(FakeH5File(), "kml/perimeter.kml")
        == (data_dir / "kml" / "perimeter.kml").resolve()
    )

    absolute_path = (tmp_path / "absolute.kml").resolve()
    assert caldor.resolve_h5_relative_path(FakeH5File(), absolute_path) == absolute_path
