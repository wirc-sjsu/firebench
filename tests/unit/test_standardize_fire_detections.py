import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import h5py
import numpy as np
import pyproj
import pytest

from firebench.acquisition import firms
from firebench.acquisition.goes_fdc import FdcScan, FetchedScan
from firebench.standardize import (
    confidence_class,
    frp_time_series,
    list_fire_detection_streams,
    merge_two_std_files,
    new_std_file,
    read_fdc_file,
    standardize_firms_bundle,
    standardize_goes_fdc,
    validate_h5_std,
)
from firebench.standardize.fire_detections import GROUP

BOX = (-120.8, 38.4, -119.7, 39.0)
START = datetime(2021, 8, 1, tzinfo=timezone.utc)
END = datetime(2021, 8, 3, tzinfo=timezone.utc)
VIIRS_HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,"
    "bright_ti5,frp,daynight,type\n"
)
MODIS_HEADER = (
    "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,"
    "bright_t31,frp,daynight,type\n"
)


def _viirs(day: str, hhmm: str, frp="4.35", confidence="n", lat="38.55") -> str:
    return f"{lat},-120.46,327.24,0.54,0.51,{day},{hhmm},N,VIIRS,{confidence},2,289.79,{frp},N,0\n"


def _modis(day: str, hhmm: str, satellite: str, confidence="86", frp="64.7") -> str:
    return f"38.58,-120.43,313.1,3,1.6,{day},{hhmm},{satellite},MODIS,{confidence},6.03,288.8,{frp},D,0\n"


def _pass(start: str, minutes: int = 6, fraction=1.0, ids=("G",)) -> dict:
    begin = datetime.fromisoformat(start)
    return {
        "time_start": begin.isoformat(),
        "time_end": (begin + timedelta(minutes=minutes)).isoformat(),
        "granule_ids": list(ids),
        "observed_fraction": fraction,
    }


def _request(product, streams, day, n_days, csv=None, status="ok") -> dict:
    return {
        "product": product,
        "streams": streams,
        "day": day,
        "n_days": n_days,
        "status": status,
        "error": None if status == "ok" else "HTTP 500 for https://firms/api/area/csv/***/",
        "csv": csv,
    }


def _bundle(tmp_path: Path, requests, overpasses, streams, uncovered=None) -> Path:
    bundle = {
        "format": firms.BUNDLE_FORMAT,
        "version": firms.BUNDLE_VERSION,
        "bbox": list(BOX),
        "start": START.isoformat(),
        "end": END.isoformat(),
        "streams": streams,
        "availability": None,
        "uncovered_days": uncovered or {},
        "requests": requests,
        "overpasses": overpasses,
    }
    return firms.write_firms_bundle(bundle, tmp_path / "firms.json")


@pytest.fixture
def std_file(tmp_path):
    file = new_std_file(tmp_path / "data.h5", "tester")
    yield file
    file.close()


@pytest.fixture
def viirs_bundle(tmp_path):
    csv = VIIRS_HEADER + _viirs("2021-08-02", "2040", frp="2.0") + _viirs("2021-08-01", "0918")
    csv += _viirs("2021-08-01", "0919", frp="1.5", confidence="h") + _viirs(
        "2021-08-01", "0918"
    )  # duplicate
    passes = [_pass("2021-08-01T09:18:00+00:00"), _pass("2021-08-01T21:00:00+00:00", fraction=0.4)]
    passes.append(_pass("2021-08-02T20:36:00+00:00"))
    return _bundle(
        tmp_path,
        [_request("VIIRS_SNPP_SP", ["viirs_snpp"], "2021-08-01", 2, csv)],
        {"viirs_snpp": {"status": "ok", "error": None, "collections": ["VNP14IMG 002"], "items": passes}},
        ["viirs_snpp"],
    )


def test_firms_stream_holds_detections_and_observations_with_their_units(std_file, viirs_bundle):
    groups = standardize_firms_bundle(viirs_bundle, std_file)

    assert [group.name for group in groups] == [f"{GROUP}/viirs_snpp"]
    group = std_file[f"{GROUP}/viirs_snpp"]
    detections, observations = group["detections"], group["observations"]
    assert group.attrs["satellite"] == "Suomi NPP" and group.attrs["observation_source"] == "cmr"
    assert bool(group.attrs["observations_complete"])
    assert json.loads(group.attrs["product"]) == ["VIIRS_SNPP_SP"] and group.attrs["product_version"] == "2"
    assert group.attrs["frame_west"] == -120.8 and group.attrs["frame_west_units"] == "degree"
    assert detections["time"].attrs["time_origin"] == START.isoformat()
    assert detections["time"].attrs["time_units"] == "s"
    assert list(detections["time"][()]) == [33480.0, 33540.0, 160800.0]  # sorted, duplicate dropped
    assert detections["fire_radiative_power"].attrs["units"] == "MW"
    assert list(detections["fire_detection_confidence"][()]) == [1, 2, 1]
    assert detections["fire_detection_confidence"].attrs["confidence_scale"] == "viirs_lnh"
    assert detections["pixel_size_scan"][0] == pytest.approx(540.0)
    assert list(detections["observation_index"][()]) == [0, 0, 2]
    assert list(observations["observed_fraction"][()]) == [1.0, 0.4, 1.0]
    assert observations["observed_fraction"].attrs["method"] == "swath"
    assert observations["granule_ids"][0] == b"G"
    assert list_fire_detection_streams(std_file) == ["viirs_snpp"]


def test_modis_is_split_into_terra_and_aqua_and_an_unknown_code_is_refused(std_file, tmp_path):
    csv = MODIS_HEADER + _modis("2021-08-01", "0520", "Terra") + _modis("2021-08-01", "0938", "Aqua")
    path = _bundle(
        tmp_path,
        [_request("MODIS_SP", ["modis_terra", "modis_aqua"], "2021-08-01", 2, csv)],
        {},
        ["modis_terra", "modis_aqua"],
    )

    standardize_firms_bundle(path, std_file)

    assert list_fire_detection_streams(std_file) == ["modis_aqua", "modis_terra"]
    terra = std_file[f"{GROUP}/modis_terra/detections"]
    assert (
        len(terra["time"]) == 1
        and terra["fire_detection_confidence"].attrs["confidence_scale"] == "modis_percent"
    )
    assert terra["brightness_temperature_mir"][0] == pytest.approx(313.1)

    bad = _bundle(
        tmp_path,
        [
            _request(
                "MODIS_SP",
                ["modis_terra", "modis_aqua"],
                "2021-08-01",
                2,
                MODIS_HEADER + _modis("2021-08-01", "0520", "X"),
            )
        ],
        {},
        ["modis_terra", "modis_aqua"],
    )
    with pytest.raises(ValueError, match=r"satellite codes \['X'\]"):
        standardize_firms_bundle(bad, std_file, overwrite=True)


def test_without_overpasses_every_observation_is_rebuilt_from_detections(std_file, tmp_path):
    csv = VIIRS_HEADER + _viirs("2021-08-01", "0918") + _viirs("2021-08-01", "0918", frp="2")
    csv += _viirs("2021-08-01", "1100")
    path = _bundle(
        tmp_path,
        [_request("VIIRS_SNPP_SP", ["viirs_snpp"], "2021-08-01", 2, csv)],
        {"viirs_snpp": {"status": "failed", "error": "HTTP 500", "collections": [], "items": []}},
        ["viirs_snpp"],
    )

    standardize_firms_bundle(path, std_file)

    group = std_file[f"{GROUP}/viirs_snpp"]
    assert group.attrs["observation_source"] == "detections" and not group.attrs["observations_complete"]
    observations = group["observations"]
    assert list(observations["time"][()]) == [33480.0, 39600.0]
    assert list(observations["time_end"][()]) == [33480.0 + 360, 39600.0 + 360]
    assert np.isnan(observations["observed_fraction"][()]).all()
    assert list(group["detections/observation_index"][()]) == [0, 0, 1]


def test_a_detection_outside_every_overpass_gets_an_observation_of_its_own(std_file, tmp_path):
    csv = VIIRS_HEADER + _viirs("2021-08-01", "0918") + _viirs("2021-08-01", "1500")
    path = _bundle(
        tmp_path,
        [_request("VIIRS_SNPP_SP", ["viirs_snpp"], "2021-08-01", 2, csv)],
        {
            "viirs_snpp": {
                "status": "ok",
                "error": None,
                "collections": [],
                "items": [_pass("2021-08-01T09:12:00+00:00")],
            }
        },
        ["viirs_snpp"],
    )

    standardize_firms_bundle(path, std_file)

    group = std_file[f"{GROUP}/viirs_snpp"]
    assert group.attrs["observation_source"] == "cmr" and not group.attrs["observations_complete"]
    assert list(group["observations/time"][()]) == [33120.0, 54000.0]
    assert list(group["detections/observation_index"][()]) == [0, 1]  # 09:18 is within 60 s of the pass end


def test_a_failed_day_loses_its_observations_and_detections(std_file, tmp_path):
    csv = VIIRS_HEADER + _viirs("2021-08-01", "0918")
    passes = [_pass("2021-08-01T09:18:00+00:00"), _pass("2021-08-02T20:36:00+00:00")]
    path = _bundle(
        tmp_path,
        [
            _request("VIIRS_SNPP_SP", ["viirs_snpp"], "2021-08-01", 1, csv),
            _request("VIIRS_SNPP_SP", ["viirs_snpp"], "2021-08-02", 1, status="failed"),
        ],
        {"viirs_snpp": {"status": "ok", "error": None, "collections": [], "items": passes}},
        ["viirs_snpp"],
    )

    standardize_firms_bundle(path, std_file)

    group = std_file[f"{GROUP}/viirs_snpp"]
    failed = json.loads(group.attrs["failed"])
    assert [item["day"] for item in failed] == ["2021-08-02"] and "***" in failed[0]["reason"]
    assert not group.attrs["observations_complete"]
    assert list(group["observations/time"][()]) == [33480.0]
    series = frp_time_series(std_file, "viirs_snpp")
    assert len(series.time) == 1  # the failed day is no pass with zero FRP


def test_a_part_of_the_window_keeps_its_rows_overpasses_and_failed_days_alone(
    std_file, tmp_path, viirs_bundle
):
    noon = START + timedelta(hours=12)
    (group,) = standardize_firms_bundle(viirs_bundle, std_file, start=noon)

    assert group.attrs["time_start"] == noon.isoformat() and group.attrs["time_end"] == END.isoformat()
    assert group["detections/time"].attrs["time_origin"] == noon.isoformat()
    assert list(group["detections/time"][()]) == [160800.0 - 43200]  # 2021-08-02 20:40 alone
    assert list(group["observations/time"][()]) == [32400.0, 160560.0 - 43200]
    assert list(group["detections/observation_index"][()]) == [1]

    csv = VIIRS_HEADER + _viirs("2021-08-02", "2040")
    failed_first_day = _bundle(
        tmp_path,
        [
            _request("VIIRS_SNPP_SP", ["viirs_snpp"], "2021-08-01", 1, status="failed"),
            _request("VIIRS_SNPP_SP", ["viirs_snpp"], "2021-08-02", 1, csv),
        ],
        {
            "viirs_snpp": {
                "status": "ok",
                "error": None,
                "collections": [],
                "items": [_pass("2021-08-02T20:36:00+00:00")],
            }
        },
        ["viirs_snpp"],
    )
    (group,) = standardize_firms_bundle(
        failed_first_day, std_file, overwrite=True, start=START + timedelta(days=1)
    )
    assert json.loads(group.attrs["failed"]) == [] and group.attrs["observations_complete"]

    with pytest.raises(ValueError, match="not a part of the bundle's"):
        standardize_firms_bundle(viirs_bundle, std_file, overwrite=True, end=END + timedelta(hours=1))
    with pytest.raises(ValueError, match="not a part of the bundle's"):
        standardize_firms_bundle(viirs_bundle, std_file, overwrite=True, start=END, end=noon)


def test_a_stream_without_answered_request_gets_no_group_and_unknown_streams_are_refused(
    std_file, tmp_path
):
    path = _bundle(
        tmp_path,
        [_request("VIIRS_SNPP_SP", ["viirs_snpp"], "2021-08-01", 2, status="failed")],
        {},
        ["viirs_snpp", "viirs_noaa21"],
        uncovered={"viirs_noaa21": ["2021-08-01", "2021-08-02"]},
    )

    assert standardize_firms_bundle(path, std_file) == []
    assert list_fire_detection_streams(std_file) == []
    with pytest.raises(ValueError, match="not in the bundle"):
        standardize_firms_bundle(path, std_file, streams=["modis_aqua"])


def test_an_existing_group_is_kept_unless_overwrite(std_file, viirs_bundle):
    standardize_firms_bundle(viirs_bundle, std_file)

    with pytest.raises(ValueError, match="already exists"):
        standardize_firms_bundle(viirs_bundle, std_file)
    assert len(standardize_firms_bundle(viirs_bundle, std_file, overwrite=True)) == 1


# GOES ------------------------------------------------------------------------------------------------

H = 35786023.0
LON_0 = -137.0
STEP = 5.6e-05


def _fdc_file(directory: Path, start: datetime, satellite: int = 17, fires=None) -> tuple[Path, dict]:
    """A small FDCC file in the netCDF4 layout over the box, with the fire pixels given."""
    proj = pyproj.Proj(proj="geos", h=H, lon_0=LON_0, sweep="x", a=6378137.0, b=6356752.31414)
    x_c, y_c = proj((BOX[0] + BOX[2]) / 2, (BOX[1] + BOX[3]) / 2)
    nx, ny = 70, 40
    x0 = round(x_c / H / STEP) * STEP - nx / 2 * STEP
    y0 = round(y_c / H / STEP) * STEP + ny / 2 * STEP
    end = start + timedelta(minutes=2, seconds=37)
    stamp = lambda moment: moment.strftime("%Y%j%H%M%S") + "7"  # noqa: E731
    name = f"OR_ABI-L2-FDCC-M6_G{satellite}_s{stamp(start)}_e{stamp(end)}_c{stamp(end)}.nc"
    path = directory / name
    mask = np.full((ny, nx), 100, dtype=np.int16)
    mask[:, :3] = 205  # a cloudy strip
    power = np.full((ny, nx), -9.0, dtype=np.float32)
    temp = np.full((ny, nx), 65535, dtype=np.uint16)
    for (row, col), (code, frp, kelvin) in (fires or {}).items():
        mask[row, col] = code
        if frp is not None:
            power[row, col] = frp
        if kelvin is not None:
            temp[row, col] = round((kelvin - 400.0) / 0.05493667)
    with h5py.File(path, "w") as nc:
        x = nc.create_dataset("x", data=np.arange(nx, dtype=np.int16))
        x.attrs.update({"scale_factor": np.float32(STEP), "add_offset": np.float32(x0)})
        y = nc.create_dataset("y", data=np.arange(ny, dtype=np.int16))
        y.attrs.update({"scale_factor": np.float32(-STEP), "add_offset": np.float32(y0)})
        nc.create_dataset("Mask", data=mask).attrs.update(
            {"_FillValue": np.int16(-99), "valid_range": np.array([0, 245], dtype=np.int16)}
        )
        nc.create_dataset("Power", data=power).attrs.update(
            {"_FillValue": np.float32(-9.0), "valid_range": np.array([0, 200000], dtype=np.float32)}
        )
        nc.create_dataset("Temp", data=temp).attrs.update(
            {
                "_FillValue": np.uint16(65535),
                "valid_range": np.array([0, 65530], dtype=np.uint16),
                "scale_factor": np.float32(0.05493667),
                "add_offset": np.float32(400.0),
            }
        )
        projection = nc.create_dataset("goes_imager_projection", data=np.int32(-2147483647))
        projection.attrs.update(
            {
                "perspective_point_height": np.array([H]),
                "semi_major_axis": np.array([6378137.0]),
                "semi_minor_axis": np.array([6356752.31414]),
                "longitude_of_projection_origin": np.array([LON_0]),
                "sweep_angle_axis": np.bytes_(b"x"),
            }
        )
        nc.attrs["platform_ID"] = np.bytes_(f"G{satellite}".encode())
    # unpacked in float32, the type of scale_factor, as CF and netCDF4 do
    x_grid = (np.arange(nx, dtype=np.int16).astype(np.float32) * np.float32(STEP) + np.float32(x0)).astype(
        np.float64
    )
    y_grid = (np.arange(ny, dtype=np.int16).astype(np.float32) * np.float32(-STEP) + np.float32(y0)).astype(
        np.float64
    )
    xx, yy = np.meshgrid(x_grid, y_grid)
    lon, lat = proj(xx * H, yy * H, inverse=True)
    return path, {
        "lon": np.asarray(lon),
        "lat": np.asarray(lat),
        "mask": mask,
        "proj": proj,
        "x": x_grid,
        "y": y_grid,
    }


def _inside(grid, row, col) -> bool:
    lon, lat = grid["lon"][row, col], grid["lat"][row, col]
    return BOX[0] <= lon <= BOX[2] and BOX[1] <= lat <= BOX[3]


def _cells_inside(grid, count: int) -> list[tuple[int, int]]:
    cells = [
        (r, c)
        for r in range(grid["lon"].shape[0])
        for c in range(3, grid["lon"].shape[1])
        if _inside(grid, r, c)
    ]
    return cells[len(cells) // 3 : len(cells) // 3 + count]


def test_read_fdc_file_decodes_the_packing_and_keeps_the_fire_pixels_in_the_box(tmp_path):
    _, grid = _fdc_file(tmp_path, START)
    cells = _cells_inside(grid, 5)
    outside = next((r, c) for r in range(40) for c in range(3, 70) if not _inside(grid, r, c))
    fires = {
        cells[0]: (10, 50.0, 900.0),
        cells[1]: (13, None, None),
        cells[2]: (15, 5.0, 650.0),
        cells[3]: (205, None, None),
        cells[4]: (205, None, None),
        outside: (10, 9.0, 800.0),
    }
    path, grid = _fdc_file(tmp_path, START + timedelta(minutes=1), fires=fires)

    scene = read_fdc_file(path, BOX)

    in_box = (
        (grid["lon"] >= BOX[0])
        & (grid["lon"] <= BOX[2])
        & (grid["lat"] >= BOX[1])
        & (grid["lat"] <= BOX[3])
    )
    assert scene.platform_id == "G17" and scene.time_start == START + timedelta(minutes=1, seconds=0)
    assert scene.n_pixels == int(in_box.sum())
    assert scene.n_assessed == int((in_box & (grid["mask"] != 205)).sum()) == scene.n_pixels - 2
    assert 0 < scene.observed_fraction < 1
    assert sorted(scene.mask.tolist()) == [10, 13, 15]
    first = list(scene.mask).index(10)
    assert scene.lon[first] == pytest.approx(grid["lon"][cells[0]], abs=1e-9)
    assert scene.lat[first] == pytest.approx(grid["lat"][cells[0]], abs=1e-9)
    assert scene.power[first] == pytest.approx(50.0) and scene.temperature[first] == pytest.approx(
        900.0, abs=0.03
    )
    assert math.isnan(scene.power[list(scene.mask).index(13)]) and math.isnan(
        scene.temperature[list(scene.mask).index(13)]
    )
    row, col = cells[0]
    sw_lon, sw_lat = grid["proj"](
        (grid["x"][col] - STEP / 2) * H, (grid["y"][row] - STEP / 2) * H, inverse=True
    )
    assert scene.footprint_lon[first, 0] == pytest.approx(sw_lon, abs=1e-6)
    assert scene.footprint_lat[first, 0] == pytest.approx(sw_lat, abs=1e-6)
    assert scene.footprint_lat[first, 2] > scene.footprint_lat[first, 0]


def _fetched(path: Path, bucket: str = "noaa-goes17") -> FetchedScan:
    from firebench.acquisition.goes_fdc import (
        scan_times,
        sha256_file,
    )  # pylint: disable=import-outside-toplevel

    return FetchedScan(
        FdcScan(bucket, f"ABI-L2-FDCC/x/{path.name}", *scan_times(path.name)), path, sha256_file(path)
    )


def _goes_stream(std_file, tmp_path):
    _, grid = _fdc_file(tmp_path, START)
    cells = _cells_inside(grid, 2)
    burning = _fdc_file(
        tmp_path,
        START + timedelta(hours=1),
        fires={cells[0]: (10, 50.0, 900.0), cells[1]: (15, 5.0, 650.0)},
    )[0]
    cloudy = _fdc_file(tmp_path, START + timedelta(hours=2), fires={cells[0]: (12, None, None)})[0]
    clear = _fdc_file(tmp_path, START + timedelta(hours=3))[0]
    missing = FetchedScan(
        FdcScan("noaa-goes17", "ABI-L2-FDCC/x/missing.nc", START + timedelta(hours=4), START),
        None,
        None,
        "HTTP 503",
    )
    scans = [_fetched(burning), _fetched(cloudy), _fetched(clear), missing]
    return standardize_goes_fdc(scans, std_file, bbox=BOX, start=START, end=END, time_step_min=60)


def test_goes_stream_holds_one_observation_per_scan_read(std_file, tmp_path):
    group = _goes_stream(std_file, tmp_path)

    assert group.name == f"{GROUP}/goes17" and group.attrs["satellite"] == "GOES-17"
    assert group.attrs["time_step"] == 60 and group.attrs["time_step_units"] == "min"
    assert not group.attrs["observations_complete"]
    assert [item["key"] for item in json.loads(group.attrs["failed"])] == ["ABI-L2-FDCC/x/missing.nc"]
    observations, detections = group["observations"], group["detections"]
    assert list(observations["time"][()]) == [3600.0, 7200.0, 10800.0]
    assert observations["observed_fraction"].attrs["method"] == "assessed_pixels"
    assert (
        observations["source_key"][0].decode().endswith(".nc")
        and len(observations["source_sha256"][0]) == 64
    )
    assert list(detections["observation_index"][()]) == [0, 0, 1]
    assert detections["footprint_lat"].shape == (3, 4)
    assert detections["fire_detection_confidence"].attrs["confidence_scale"] == "goes_fdc_mask"
    assert "pixel_size_scan" not in detections


def test_scans_of_two_buckets_or_none_readable_are_refused(std_file, tmp_path):
    first = _fdc_file(tmp_path, START)[0]
    second = _fdc_file(tmp_path, START + timedelta(hours=1), satellite=16)[0]

    with pytest.raises(ValueError, match="cannot share one stream"):
        standardize_goes_fdc(
            [_fetched(first), _fetched(second, "noaa-goes16")],
            std_file,
            bbox=BOX,
            start=START,
            end=END,
            time_step_min=30,
        )
    with pytest.raises(ValueError, match="no GOES scan could be read"):
        standardize_goes_fdc(
            [FetchedScan(FdcScan("noaa-goes17", "k", START, START), None, None, "x")],
            std_file,
            bbox=BOX,
            start=START,
            end=END,
            time_step_min=30,
        )


# Merge, series, classes ----------------------------------------------------------------------------


def test_firms_and_goes_fragments_merge_without_conflict(tmp_path, viirs_bundle):
    (tmp_path / "goes").mkdir()
    with new_std_file(tmp_path / "firms.h5", "tester") as firms_file:
        standardize_firms_bundle(viirs_bundle, firms_file)
    with new_std_file(tmp_path / "goes.h5", "tester") as goes_file:
        _goes_stream(goes_file, tmp_path / "goes")

    merge_two_std_files(str(tmp_path / "firms.h5"), str(tmp_path / "goes.h5"), str(tmp_path / "merged.h5"))

    with h5py.File(tmp_path / "merged.h5", "r") as merged:
        validate_h5_std(merged)
        assert list_fire_detection_streams(merged) == ["goes17", "viirs_snpp"]
        assert dict(merged["unstructured"].attrs) == {} and dict(merged[GROUP].attrs) == {}
        assert merged[f"{GROUP}/goes17/detections/footprint_lon"].shape == (3, 4)
        assert len(frp_time_series(merged, "goes17").time) == 3


def test_frp_series_tells_zero_from_missing_and_applies_window_box_and_confidence(std_file, tmp_path):
    _goes_stream(std_file, tmp_path)

    series = frp_time_series(std_file, "goes17")
    assert series.time.tolist() == [
        datetime(2021, 8, 1, hour) for hour in (1, 2, 3)
    ]  # no entry for the scan that failed
    assert series.frp_total[0] == pytest.approx(55.0) and series.n_detections.tolist() == [2, 1, 0]
    assert math.isnan(series.frp_total[1]) and series.frp_total[2] == 0.0

    nominal = frp_time_series(std_file, "goes17", min_confidence="nominal")
    assert nominal.frp_total[0] == pytest.approx(50.0) and nominal.frp_total[1] == 0.0
    later = frp_time_series(std_file, "goes17", start=START + timedelta(hours=1, minutes=30))
    assert later.n_detections.tolist() == [1, 0]
    nowhere = frp_time_series(std_file, "goes17", corners=((10.0, 10.0), (11.0, 11.0)))
    assert nowhere.frp_total.tolist() == [0.0, 0.0, 0.0]
    with pytest.raises(ValueError, match="no fire detection stream"):
        frp_time_series(std_file, "goes18")
    with pytest.raises(ValueError, match="min_confidence"):
        frp_time_series(std_file, "goes17", min_confidence="medium")


def test_frp_series_reads_a_file_by_path(tmp_path, viirs_bundle):
    with new_std_file(tmp_path / "f.h5", "tester") as file:
        standardize_firms_bundle(viirs_bundle, file)

    series = frp_time_series(tmp_path / "f.h5", "viirs_snpp", min_confidence="high")

    assert series.frp_total.tolist() == [1.5, 0.0, 0.0]
    assert series.observed_fraction.tolist() == [1.0, 0.4, 1.0]


@pytest.mark.parametrize(
    "scale, values, classes",
    [
        ("viirs_lnh", [0, 1, 2, -1], [0, 1, 2, -1]),
        ("modis_percent", [0, 29, 30, 79, 80, 100, -1, 101], [0, 0, 1, 1, 2, 2, -1, -1]),
        (
            "goes_fdc_mask",
            [10, 11, 12, 13, 14, 15, 30, 31, 32, 33, 34, 35, 100],
            [2, 2, 0, 2, 1, 0, 2, 2, 0, 2, 1, 0, -1],
        ),
    ],
)
def test_confidence_classes(scale, values, classes):
    assert confidence_class(values, scale).tolist() == classes


def test_unknown_confidence_scale_is_refused():
    with pytest.raises(ValueError, match="unknown confidence scale"):
        confidence_class([1], "other")
