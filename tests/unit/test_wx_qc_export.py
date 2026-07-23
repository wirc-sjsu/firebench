"""Focused tests for weather-station QC export contracts."""

import ast
import hashlib
import json
from types import SimpleNamespace

import h5py
import numpy as np
import pytest

from firebench.tools.wx_qc.tabs.skiplist import (
    _format_remove_records_block,
    _format_skip_stations_block,
    SkiplistTabMixin,
    build_processing_script_text,
    write_cleaned_h5,
)


def _add_h5_station(time_series, station_id, values):
    station = time_series.create_group(f"station_{station_id}")
    time = station.create_dataset("time", data=np.array([0.0, 60.0, 120.0]))
    time.attrs["time_origin"] = "2020-01-01T00:00:00+00:00"
    time.attrs["time_units"] = "min"
    station.create_dataset("air_temperature", data=np.array(values, dtype=float))


def _raw_station(station_id):
    return {
        "STID": station_id,
        "NAME": f"Station {station_id}",
        "ID": 1,
        "MNET_ID": 1,
        "STATE": "CA",
        "TIMEZONE": "UTC",
        "LATITUDE": 38.0,
        "LONGITUDE": -120.0,
        "ELEVATION": 1000.0,
        "ELEV_DEM": 1000.0,
        "UNITS": {"elevation": "m"},
        "PROVIDERS": [{"name": "Test"}],
        "SENSOR_VARIABLES": {
            "air_temperature": {"air_temp_set_1": {"position": 2.0}},
        },
        "OBSERVATIONS": {
            "date_time": ["2020-01-01T00:00:00Z", "2020-01-01T00:01:00Z"],
            "air_temp_set_1": [10.0, 11.0],
        },
    }


def test_python_exports_safely_serialize_difficult_text():
    station_id = "A'\"\\\n雪"
    reason = "bad ' \" \\\nline two ☃"
    removal = {
        station_id: [
            {
                "var": "air_'\"\\\n温度",
                "t0": "2020-01-01T00:00:00\n",
                "t1": "2020-01-01T01:00:00\\",
                "reason": reason,
            }
        ]
    }

    source = _format_skip_stations_block({station_id: reason})
    source += "\n" + _format_remove_records_block(removal)
    ast.parse(source)
    namespace = {}
    exec(compile(source, "<decision-export>", "exec"), namespace)

    assert namespace["skip_stations"] == [station_id]
    assert namespace["skip_reasons"] == {station_id: reason}
    assert namespace["remove_records"][station_id][0] == (
        removal[station_id][0]["var"],
        removal[station_id][0]["t0"],
        removal[station_id][0]["t1"],
        reason,
    )


def test_decision_file_is_written_as_utf8_python(tmp_path):
    destination = tmp_path / "decisions.py"
    state = SimpleNamespace(
        skip_list={"雪": "quote ' slash \\ newline\n☃"},
        removal_list={},
        h5_path=None,
    )

    SkiplistTabMixin._skip_export_write(state, destination)
    source = destination.read_text(encoding="utf-8")

    ast.parse(source)
    assert "雪" in source
    assert not list(tmp_path.glob(f".{destination.name}.*.tmp"))


def test_cleaned_h5_omits_skips_applies_removals_and_preserves_source(tmp_path):
    source = tmp_path / "source.h5"
    destination = tmp_path / "cleaned.h5"
    with h5py.File(source, "w") as h5_file:
        time_series = h5_file.create_group("time_series")
        _add_h5_station(time_series, "SKIP", [4.0, 5.0, 6.0])
        _add_h5_station(time_series, "KEEP", [1.0, np.nan, 3.0])
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    destination.write_bytes(b"old destination")

    result = write_cleaned_h5(
        source,
        destination,
        {"SKIP": "bad station"},
        {
            "KEEP": [
                {
                    "var": "air_temperature",
                    "t0": "2020-01-01T01:00:00",
                    "t1": "2020-01-01T02:00:00",
                    "reason": "bad range",
                }
            ]
        },
    )

    assert result == (1, 1, 1, [])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_digest
    with h5py.File(source, "r") as source_h5:
        assert "station_SKIP" in source_h5["time_series"]
        np.testing.assert_allclose(
            source_h5["time_series/station_KEEP/air_temperature"][:],
            [1.0, np.nan, 3.0],
            equal_nan=True,
        )
    with h5py.File(destination, "r") as cleaned_h5:
        assert "station_SKIP" not in cleaned_h5["time_series"]
        np.testing.assert_allclose(
            cleaned_h5["time_series/station_KEEP/air_temperature"][:],
            [1.0, np.nan, np.nan],
            equal_nan=True,
        )
    assert not list(tmp_path.glob(f".{destination.name}.*.tmp"))


def test_cleaned_h5_rejects_source_as_destination(tmp_path):
    source = tmp_path / "source.h5"
    source.write_bytes(b"source bytes")

    with pytest.raises(ValueError, match="must differ"):
        write_cleaned_h5(source, source, {}, {})

    assert source.read_bytes() == b"source bytes"


def test_cleaned_h5_failure_preserves_existing_destination(tmp_path):
    source = tmp_path / "invalid.h5"
    destination = tmp_path / "existing.h5"
    source.write_bytes(b"not an HDF5 file")
    destination.write_bytes(b"existing destination")

    with pytest.raises(OSError):
        write_cleaned_h5(source, destination, {}, {})

    assert destination.read_bytes() == b"existing destination"
    assert not list(tmp_path.glob(f".{destination.name}.*.tmp"))


def test_generated_processing_script_runs_minimal_workflow(tmp_path):
    json_path = tmp_path / "weather ' 雪.json"
    output_path = tmp_path / 'standardized " 雪.h5'
    json_path.write_text(
        json.dumps({"STATION": [_raw_station("KEEP"), _raw_station("SKIP")]}, ensure_ascii=False),
        encoding="utf-8",
    )
    description = "description with ' \" \\\n雪"
    contributors = "O'Brien; 雪"
    fields = {
        "fire_name": "Test fire",
        "json_filename": str(json_path),
        "output_h5_filename": str(output_path),
        "description": description,
        "contributors": contributors,
        "compression_lvl": 1,
        "logging_lvl": 30,
        "dest_dir": str(tmp_path),
        "script_filename": "process ' 雪.py",
    }
    removal_list = {
        "KEEP": [
            {
                "var": "air_temperature",
                "t0": "2020-01-01T00:01:00",
                "t1": "2020-01-01T00:01:00",
                "reason": "sensor ' \" \\\n雪",
            }
        ]
    }

    script = build_processing_script_text({"SKIP": "reject ' \" \\\n雪"}, removal_list, fields)
    ast.parse(script)
    exec(compile(script, str(tmp_path / fields["script_filename"]), "exec"), {"__name__": "__main__"})

    with h5py.File(output_path, "r") as output_h5:
        assert output_h5.attrs["created_by"] == contributors
        assert output_h5.attrs["description"] == description
        assert set(output_h5["time_series"]) == {"station_KEEP"}
        np.testing.assert_allclose(
            output_h5["time_series/station_KEEP/air_temperature"][:],
            [10.0, np.nan],
            equal_nan=True,
        )
    assert not list(tmp_path.glob(f".{output_path.name}.*.tmp"))
