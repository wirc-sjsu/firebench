from pathlib import Path

from firebench.benchmarks import c001_caldor


def test_build_registries_is_fresh():
    c001_caldor.build_registries()
    first_r08_count = len(c001_caldor.REQUIREMENTS["R08"]["benchmarks"])
    first_benchmark_count = len(c001_caldor.BENCHMARK_FUNCTIONS)

    c001_caldor.build_registries()

    assert len(c001_caldor.REQUIREMENTS["R08"]["benchmarks"]) == first_r08_count
    assert len(c001_caldor.BENCHMARK_FUNCTIONS) == first_benchmark_count
    assert first_r08_count == 1188


def test_hrrr_weather_aggregation_schemes_are_generated():
    c001_caldor.build_registries()

    assert "WX_WH1" in c001_caldor.AGGREGATION
    assert "WX_WH62" in c001_caldor.AGGREGATION
    assert "WX_WH_ALL" in c001_caldor.AGGREGATION
    assert list(c001_caldor.AGGREGATION["WX_WH1"]) == [
        "Air Temp WH1",
        "RH WH1",
        "Wind Speed WH1",
        "Wind Direction WH1",
        "FMC 10h WH1",
    ]
    assert len(c001_caldor.AGGREGATION["WX_WH_ALL"]) == 5 * len(c001_caldor.WH_PERIODS)


def test_describe_benchmark_registry_prints_selected_groups():
    description = c001_caldor.describe_benchmark_registry("WX_WH1")

    assert "Aggregation scheme: WX_WH1" in description
    assert "Selected groups: 5" in description
    assert "- Air Temp WH1" in description
    assert "- RH WH1" in description
    assert "FB001_WX" in description
    assert "Air temp" in description


def test_get_list_benchmark_with_aggregation_scheme():
    c001_caldor.build_registries()

    assert c001_caldor.get_list_benchmark_with_agg(c001_caldor.AGGREGATION, "B") == [
        "FB001_BD01",
        "FB001_BD02",
        "FB001_BD03",
        "FB001_BD04",
        "FB001_BD05",
        "FB001_BD06",
    ]
    assert set(c001_caldor.get_list_benchmark_with_agg(c001_caldor.AGGREGATION, "0")) == set(
        c001_caldor.BENCHMARK_FUNCTIONS
    )


def test_overwrite_previous_run(monkeypatch, tmp_path):
    output_path = tmp_path / "Caldor_rslt.json"

    assert c001_caldor.overwrite_previous_run(False, output_path) is True

    output_path.write_text("{}")
    assert c001_caldor.overwrite_previous_run(True, output_path) is True

    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert c001_caldor.overwrite_previous_run(False, output_path) is False

    monkeypatch.setattr("builtins.input", lambda _: "yes")
    assert c001_caldor.overwrite_previous_run(False, output_path) is True


def test_resolve_h5_relative_path(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    class FakeH5File:
        filename = str(data_dir / "Caldor.h5")

    assert (
        c001_caldor.resolve_h5_relative_path(FakeH5File(), "kml/perimeter.kml")
        == (data_dir / "kml" / "perimeter.kml").resolve()
    )

    absolute_path = (tmp_path / "absolute.kml").resolve()
    assert c001_caldor.resolve_h5_relative_path(FakeH5File(), absolute_path) == absolute_path
