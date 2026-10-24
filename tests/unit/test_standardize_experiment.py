import json

import h5py
import numpy as np
import pytest

from firebench.standardize import (
    ColumnRecipe,
    GeographicPosition,
    ReaderRecipe,
    ReferencePoint,
    RelativePosition,
    SensorRow,
    SensorSheet,
    TableRecipe,
    TimeRecipe,
    experiment_geographic,
    experiment_variables,
    list_experiment_sensors,
    new_std_file,
    read_sensor_sheet,
    read_sensor_table,
    sniff_table,
    table_recipe_schema,
    validate_h5_std,
    write_sensor,
)

PLOT = ReferencePoint("plot", 29.4, -95.0, 10.0)
CST = -6.0

# Shapes of FireFlux I's files, a few rows each.
SONIC = """2006              2             23             12              0              1              1      5.5128407     0.55980736     0.71336342      14.284615
2006              2             23             12              0              2              2      6.1795475    -0.53675296    -0.53645095       14.17938
2006              2             23             12              0              3              3      6.5905925    -0.83275428    -0.28805306       14.15676
"""
THERMOCOUPLES = (
    "TIMESTAMP\tCounter-seconds\ttc_ref\tTC_01m\tTC_2m\tTC_Fuel_0.13m\n"
    "2/23/2006 12:30\t1\t18.781\t18.53601\t17.99014\t20.11779\n"
    "2/23/2006 12:30\t2\t18.78148\t17.90801\t17.85674\t20.21595\n"
    "2/23/2006 12:30\t3\t18.78207\t18.61666\t18.02707\t19.96618\n"
)
TETHERSONDE = """ f-day,    pr(mb),   ta(C),   RH(%), Q(q/kg),    Z(m), ws(m/s), wd(deg), hh:mm,  #obs
10.06667,  1017.8,    14.5,    78.7,     8.0,     6.0,     7.2,   329.0, 10:04,   1
10.08333,  1017.8,    14.4,    78.3,     7.9,     5.8,     7.3,   336.6, 10:05,   5
10.10000,  1017.6,    14.1,    79.1,     7.8,     7.2,     7.4,   336.8, 10:06,   5
"""
STATION = (
    "YEAR,DOY,HOUR,BATT,WS,WD,TC,RH\n2006,54,1158,12.2,3.1,170,14.2,80\n2006,54,1200,12.2,3.4,172,14.3,79\n"
)
STANDARD = (
    "time,wind_speed_u[m/s],air_temperature[degC]\n"
    "2006-02-23T12:00:01-06:00,1.5,14.0\n"
    "2006-02-23T12:00:02-06:00,1.6,14.1\n"
)


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def std_file(tmp_path):
    file = new_std_file(tmp_path / "data.h5", "tester")
    yield file
    file.close()


def _sonic_recipe(**changes):
    columns = (
        ColumnRecipe("column_8", "wind_speed_u", "m/s"),
        ColumnRecipe("column_9", "wind_speed_v", "m/s"),
        ColumnRecipe("column_10", "wind_speed_w", "m/s"),
        ColumnRecipe("column_11", "sonic_temperature", "degC"),
    )
    roles = ("year", "month", "day", "hour", "minute", "second")
    time = TimeRecipe("components", {role: f"column_{index}" for index, role in enumerate(roles, start=1)})
    values = {"reader": ReaderRecipe(header=False), "columns": columns, "time": time, "utc_offset": CST}
    return TableRecipe(**(values | changes))


def _sheet(*rows, points=(PLOT,)):
    return SensorSheet(reference_points=points, sensors=rows)


def test_sonic_columns_with_date_parts_in_local_time(tmp_path):
    path = _write(tmp_path, "Pfit_MT42m.dat", SONIC)
    sniff = sniff_table(path)
    assert sniff.reader.delimiter is None and not sniff.reader.header
    assert sniff.columns[:2] == ["column_1", "column_2"] and sniff.n_rows == 3
    table = read_sensor_table(path, _sonic_recipe())
    assert str(table.time[0]) == "2006-02-23T18:00:01.000"
    assert table.column("wind_speed_u").values[0] == pytest.approx(5.5128407)
    assert table.column("sonic_temperature").values[0] == pytest.approx(287.434615)


def test_the_utc_offset_is_never_guessed(tmp_path):
    path = _write(tmp_path, "sonic.dat", SONIC)
    sniff = sniff_table(path, _sonic_recipe(utc_offset=None))
    assert sniff.first_time is None and "UTC offset" in sniff.time_problem
    sniff = sniff_table(path, _sonic_recipe())
    assert (sniff.first_time, sniff.last_time) == ("2006-02-23T18:00:01Z", "2006-02-23T18:00:03Z")


def test_thermocouples_counted_from_a_start(tmp_path):
    path = _write(tmp_path, "tc_data_1hz_2.txt", THERMOCOUPLES)
    sniff = sniff_table(path)
    assert sniff.reader.delimiter == "\t" and sniff.reader.header
    recipe = TableRecipe(
        reader=sniff.reader,
        columns=(
            ColumnRecipe("TC_01m", "air_temperature", "degC", 1.0),
            ColumnRecipe("TC_2m", "air_temperature", "degC", 2.0),
            ColumnRecipe("TC_Fuel_0.13m", "temperature", "degC", 0.13),
        ),
        time=TimeRecipe(
            "counter", {"counter": "Counter-seconds"}, start="2006-02-23T12:30:00", counter_origin=1
        ),
        utc_offset=CST,
    )
    table = read_sensor_table(path, recipe)
    assert str(table.time[0]) == "2006-02-23T18:30:00.000"
    assert str(table.time[-1]) == "2006-02-23T18:30:02.000"


def test_tethersonde_decimal_hours_of_a_date(tmp_path):
    path = _write(tmp_path, "Y2524067_01.1-min.m.txt", TETHERSONDE)
    sniff = sniff_table(path)
    assert sniff.reader.delimiter == "," and sniff.columns[0] == "f-day"
    recipe = TableRecipe(
        reader=sniff.reader,
        columns=(
            ColumnRecipe("pr(mb)", "air_pressure", "mbar"),
            ColumnRecipe("ta(C)", "air_temperature", "degC"),
            ColumnRecipe("Z(m)", "position_z", "m"),
        ),
        time=TimeRecipe("date_decimal_hours", {"hours": "f-day"}, date="2006-02-23"),
        utc_offset=CST,
    )
    table = read_sensor_table(path, recipe)
    assert str(table.time[0]) == "2006-02-23T16:04:00.000"
    assert table.column("air_pressure").values[0] == pytest.approx(101780.0)


def test_station_year_day_of_year_and_hhmm(tmp_path):
    path = _write(tmp_path, "station.csv", STATION)
    sniff = sniff_table(path)
    assert sniff.recipe.time.kind == "year_doy_hhmm"
    assert sniff.recipe.time.columns == {"year": "YEAR", "doy": "DOY", "hhmm": "HOUR"}
    recipe = TableRecipe(
        reader=sniff.reader,
        columns=(ColumnRecipe("RH", "relative_humidity", "%"),),
        time=sniff.recipe.time,
        utc_offset=CST,
    )
    table = read_sensor_table(path, recipe)
    assert [str(value) for value in table.time] == ["2006-02-23T17:58:00.000", "2006-02-23T18:00:00.000"]


def test_radiosonde_workbook_seconds_from_launch(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Sheet1"
    sheet.append(["Time(s)", "T(K)", "Height(m AGL)", "P(mb)"])
    for row in ([0, 288.2, 10, 1017.1], [2, 287.8, 16, 1016.4], [4, 287.7, 27, 1015.1]):
        sheet.append(row)
    path = tmp_path / "radiosonde.xlsx"
    book.save(path)
    sniff = sniff_table(path)
    assert sniff.reader.kind == "workbook" and sniff.sheets == ["Sheet1"] and sniff.reader.header
    recipe = TableRecipe(
        reader=sniff.reader,
        columns=(
            ColumnRecipe("T(K)", "air_temperature", "K"),
            ColumnRecipe("Height(m AGL)", "position_z", "m"),
        ),
        time=TimeRecipe("counter", {"counter": "Time(s)"}, start="2006-02-23T06:55:00"),
        utc_offset=CST,
    )
    table = read_sensor_table(path, recipe)
    assert str(table.time[0]) == "2006-02-23T12:55:00.000"


def test_a_sensor_table_needs_no_mapping(tmp_path):
    path = _write(tmp_path, "sensor.csv", STANDARD)
    sniff = sniff_table(path)
    assert sniff.recipe.time.kind == "iso"
    assert [(column.variable, column.unit) for column in sniff.recipe.columns] == [
        ("wind_speed_u", "m/s"),
        ("air_temperature", "degC"),
    ]
    assert sniff.first_time == "2006-02-23T18:00:01Z" and sniff.time_problem is None
    table = read_sensor_table(path, sniff.recipe)
    assert table.column("air_temperature").values[1] == pytest.approx(287.25)


def test_a_recipe_refuses_what_cannot_be_read(tmp_path):
    path = _write(tmp_path, "sonic.dat", SONIC)
    with pytest.raises(ValueError, match="millibarn"):
        TableRecipe.from_dict(
            _sonic_recipe(columns=(ColumnRecipe("column_8", "air_pressure", "mb"),)).to_dict()
        )
    with pytest.raises(ValueError, match="Pint does not know"):
        read_sensor_table(
            path, _sonic_recipe(columns=(ColumnRecipe("column_8", "wind_speed_u", "bogons/s"),))
        )
    with pytest.raises(ValueError, match="both give wind_speed_u"):
        read_sensor_table(
            path,
            _sonic_recipe(
                columns=(
                    ColumnRecipe("column_8", "wind_speed_u", "m/s"),
                    ColumnRecipe("column_9", "wind_speed_u", "m/s"),
                )
            ),
        )
    backwards = SONIC.splitlines()
    backwards[1], backwards[2] = backwards[2], backwards[1]
    with pytest.raises(ValueError, match="Data row 3 goes back"):
        read_sensor_table(_write(tmp_path, "back.dat", "\n".join(backwards)), _sonic_recipe())


def test_recipe_round_trips_through_json():
    recipe = _sonic_recipe(missing_values=("-9999",))
    again = TableRecipe.from_dict(json.loads(json.dumps(recipe.to_dict())))
    assert again == recipe
    schema = table_recipe_schema()
    assert set(schema["properties"]) == set(recipe.to_dict())
    with pytest.raises(ValueError, match="no field colour"):
        TableRecipe.from_dict(recipe.to_dict() | {"colour": "red"})


def test_variables_carry_their_units():
    variables = {item["name"]: item for item in experiment_variables()}
    assert variables["relative_humidity"]["units"] == "percent"
    assert variables["air_pressure"]["units"] == "Pa"
    assert variables["position_z"]["position"]


def test_both_position_conventions(tmp_path, std_file):
    path = _write(tmp_path, "sonic.dat", SONIC)
    table = read_sensor_table(path, _sonic_recipe())
    east = SensorRow("sonic_42m", "main_tower", "fixed", RelativePosition("plot", 100.0, 0.0), height=42.0)
    station = SensorRow("sonic", "north", "fixed", GeographicPosition(29.42, -95.0, 12.0), height=2.0)
    sheet = _sheet(east, station)
    (relative,) = write_sensor(std_file, east, table, sheet)
    (geographic,) = write_sensor(std_file, station, table, sheet)
    platform = std_file["/time_series/main_tower"]
    assert platform.attrs["position_origin_name"] == "plot" and platform.attrs["position_x"] == 100.0
    assert "position_lat" not in platform.attrs
    lon, lat, _ = experiment_geographic(relative)
    assert lon[0] - PLOT.lon == pytest.approx(0.00103, abs=1e-5) and lat[0] == pytest.approx(PLOT.lat)
    lon, lat, alt = experiment_geographic(geographic)
    assert (lon[0], lat[0], alt[0]) == (-95.0, 29.42, 12.0)
    assert relative["wind_speed_u"].attrs["sensor_height"] == 42.0
    assert relative.attrs["source_sha256"] and relative.attrs["sensor_kind"] == "fixed"
    assert list_experiment_sensors(std_file) == [
        "/time_series/main_tower/sonic_42m",
        "/time_series/north/sonic",
    ]
    validate_h5_std(std_file)


def test_a_rotated_survey(tmp_path, std_file):
    rotated = ReferencePoint("plot", 29.4, -95.0, 10.0, axes_azimuth=90.0)
    row = SensorRow("sonic", "tower", "fixed", RelativePosition("plot", 0.0, 100.0), height=2.0)
    (group,) = write_sensor(
        std_file,
        row,
        read_sensor_table(_write(tmp_path, "s.dat", SONIC), _sonic_recipe()),
        _sheet(row, points=(rotated,)),
    )
    lon, lat, _ = experiment_geographic(group)
    assert lon[0] - rotated.lon == pytest.approx(0.00103, abs=1e-5)
    assert lat[0] == pytest.approx(rotated.lat, abs=1e-7)


def test_a_platform_has_one_position(tmp_path, std_file):
    table = read_sensor_table(_write(tmp_path, "s.dat", SONIC), _sonic_recipe())
    relative = SensorRow("a", "tower", "fixed", RelativePosition("plot", 10.0, 0.0), height=2.0)
    geographic = SensorRow("b", "tower", "fixed", GeographicPosition(29.4, -95.0, 10.0), height=10.0)
    with pytest.raises(ValueError, match="mix geographic and relative"):
        write_sensor(std_file, relative, table, _sheet(relative, geographic))
    elsewhere = SensorRow("b", "tower", "fixed", RelativePosition("plot", 20.0, 0.0), height=10.0)
    with pytest.raises(ValueError, match="different positions"):
        write_sensor(std_file, relative, table, _sheet(relative, elsewhere))
    lost = SensorRow("c", "mast", "fixed", RelativePosition("corner", 0.0, 0.0), height=2.0)
    with pytest.raises(ValueError, match="no reference point named corner"):
        write_sensor(std_file, lost, table, _sheet(lost))
    write_sensor(std_file, relative, table, _sheet(relative))
    with pytest.raises(ValueError, match="another position"):
        write_sensor(std_file, elsewhere, table, _sheet(elsewhere))


def test_wind_signed_the_other_way_is_turned(tmp_path, std_file):
    row = SensorRow(
        "s",
        "t",
        "fixed",
        GeographicPosition(29.4, -95.0, 10.0),
        height=2.0,
        wind_convention="u_west_v_south",
    )
    table = read_sensor_table(_write(tmp_path, "s.dat", SONIC), _sonic_recipe())
    (group,) = write_sensor(std_file, row, table, _sheet(row))
    assert group["wind_speed_u"][0] == pytest.approx(-5.5128407)
    assert group["wind_speed_w"][0] == pytest.approx(0.71336342)
    assert group.attrs["wind_convention_source"] == "u_west_v_south"


def test_an_array_by_height(tmp_path, std_file):
    path = _write(tmp_path, "tc.txt", THERMOCOUPLES)
    recipe = TableRecipe(
        reader=ReaderRecipe(delimiter="\t"),
        columns=(
            ColumnRecipe("TC_2m", "air_temperature", "degC", 2.0),
            ColumnRecipe("TC_01m", "air_temperature", "degC", 1.0),
            ColumnRecipe("TC_Fuel_0.13m", "temperature", "degC", 0.13),
        ),
        time=TimeRecipe(
            "counter", {"counter": "Counter-seconds"}, start="2006-02-23T12:30:00", counter_origin=1
        ),
        utc_offset=CST,
    )
    row = SensorRow("tc", "main_tower", "array", RelativePosition("plot", 100.0, 0.0))
    groups = write_sensor(std_file, row, read_sensor_table(path, recipe), _sheet(row))
    assert [group.name for group in groups] == [
        "/spatial_1d/main_tower/tc_air_temperature",
        "/spatial_1d/main_tower/tc_temperature",
    ]
    air = groups[0]
    assert list(air["position_z"][()]) == [1.0, 2.0]
    assert air["air_temperature"].shape == (3, 2)
    assert air["air_temperature"][0, 0] == pytest.approx(18.53601 + 273.15)
    fixed = SensorRow("tc", "main_tower", "fixed", RelativePosition("plot", 100.0, 0.0), height=2.0)
    with pytest.raises(ValueError, match="a height per column is for an array"):
        write_sensor(std_file, fixed, read_sensor_table(path, recipe), _sheet(fixed))


def test_a_sounding_relative_to_its_platform(tmp_path, std_file):
    path = _write(tmp_path, "sonde.txt", TETHERSONDE)
    recipe = TableRecipe(
        reader=ReaderRecipe(delimiter=","),
        columns=(ColumnRecipe("ta(C)", "air_temperature", "degC"), ColumnRecipe("Z(m)", "position_z", "m")),
        time=TimeRecipe("date_decimal_hours", {"hours": "f-day"}, date="2006-02-23"),
        utc_offset=CST,
    )
    row = SensorRow("sonde_01", "tether", "moving", RelativePosition("plot", 0.0, 50.0, 1.0))
    (group,) = write_sensor(std_file, row, read_sensor_table(path, recipe), _sheet(row))
    assert list(group["position_z"][()]) == [7.0, 6.8, 8.2]
    assert list(group["position_y"][()]) == [50.0, 50.0, 50.0]
    assert group.attrs["launch_time"] == "2006-02-23T16:04:00Z"
    _, lat, alt = experiment_geographic(group)
    assert lat.shape == (3,) and lat[0] > PLOT.lat and alt[0] == pytest.approx(17.0, abs=0.01)
    with pytest.raises(ValueError, match="only a moving sensor"):
        still = SensorRow("still", "tether", "fixed", RelativePosition("plot", 0.0, 50.0, 1.0), height=1.0)
        write_sensor(std_file, still, read_sensor_table(path, recipe), _sheet(still))


def test_sensor_sheets_in_csv_and_yaml(tmp_path):
    csv_sheet = _write(
        tmp_path,
        "sheet.csv",
        "id,platform,kind,file,lat,lon,alt,reference,x,y,z,height\n"
        "plot,,reference,,29.4,-95.0,10,,,,,\n"
        "sonic_42m,main_tower,fixed,sonic.dat,,,,plot,100,0,0,42\n",
    )
    sheet = read_sensor_sheet(csv_sheet)
    assert sheet.reference("plot").alt == 10.0
    assert sheet.row_for_file("sonic.dat").position == RelativePosition("plot", 100.0, 0.0, 0.0)
    yaml_sheet = _write(
        tmp_path,
        "sheet.yaml",
        "reference_points: []\nsensors:\n  - {id: s, platform: p, kind: fixed, lat: 29.4, lon: -95, alt: 3, height: 2}\n",
    )
    assert read_sensor_sheet(yaml_sheet).sensors[0].position == GeographicPosition(29.4, -95.0, 3.0)
    mixed = _write(
        tmp_path, "mixed.csv", "id,platform,kind,lat,lon,alt,reference,x,y\ns,p,fixed,29,-95,1,plot,1,2\n"
    )
    with pytest.raises(ValueError, match="line 2.*not both"):
        read_sensor_sheet(mixed)


def test_written_file_holds_float_time(tmp_path):
    path = tmp_path / "out.h5"
    with new_std_file(path, "tester") as h5:
        row = SensorRow("s", "t", "fixed", GeographicPosition(29.4, -95.0, 10.0), height=2.0)
        write_sensor(
            h5, row, read_sensor_table(_write(tmp_path, "s.dat", SONIC), _sonic_recipe()), _sheet(row)
        )
    with h5py.File(path) as h5:
        time = h5["/time_series/t/s/time"]
        assert time.dtype == np.float64 and list(time[()]) == [0.0, 1.0, 2.0]
        assert time.attrs["time_origin"] == "2006-02-23T18:00:01+00:00"
