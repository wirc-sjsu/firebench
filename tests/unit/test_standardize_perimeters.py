import hashlib
import zipfile

import geopandas as gpd
import pytest
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon

import firebench.standardize as fs

TIME = "2021-08-17T20:20-07:00"
SQUARE_A1 = [(-120.5, 38.5), (-120.4, 38.5), (-120.4, 38.6), (-120.5, 38.6), (-120.5, 38.5)]
SQUARE_A2 = [(-120.3, 38.5), (-120.2, 38.5), (-120.2, 38.6), (-120.3, 38.6), (-120.3, 38.5)]
SQUARE_B = [(-120.5, 38.7), (-120.25, 38.7), (-120.25, 38.8), (-120.5, 38.8), (-120.5, 38.7)]
HOLE_1 = [(-120.45, 38.72), (-120.45, 38.76), (-120.4, 38.76), (-120.4, 38.72), (-120.45, 38.72)]
HOLE_2 = [(-120.35, 38.74), (-120.35, 38.78), (-120.3, 38.78), (-120.3, 38.74), (-120.35, 38.74)]
ACRE_IN_M2 = 43560 * (1200 / 3937) ** 2  # the US survey acre, which is the acre of pint


def _linear_ring(ring):
    coordinates = " ".join(f"{lon!r},{lat!r},0" for lon, lat in ring)
    return f"<LinearRing><coordinates>{coordinates}</coordinates></LinearRing>"


def _polygon_placemark(ring, inner_boundaries=()):
    """A polygon placemark. Each inner boundary is a list of rings: standard KML has one ring in each."""
    inner = "".join(
        f"<innerBoundaryIs>{''.join(_linear_ring(hole) for hole in holes)}</innerBoundaryIs>"
        for holes in inner_boundaries
    )
    return (
        "<Placemark><name>polygon</name><Polygon>"
        f"<outerBoundaryIs>{_linear_ring(ring)}</outerBoundaryIs>{inner}"
        "</Polygon></Placemark>"
    )


def _point_placemark(lon, lat):
    return f"<Placemark><name>point</name><Point><coordinates>{lon!r},{lat!r},0</coordinates></Point></Placemark>"


def _kml_text(folders):
    body = "".join(
        f"<Folder><name>{name}</name>{''.join(placemarks)}</Folder>" for name, placemarks in folders.items()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<kml xmlns="http://www.opengis.net/kml/2.2"><Document>{body}</Document></kml>'
    )


def _stored_polygons(group, h5_dir):
    """The polygons of the KML file a group references, as one 2-D geometry."""
    stored = gpd.read_file(h5_dir / group.attrs["rel_path"])
    return shapely.force_2d(stored.union_all())


@pytest.fixture
def bundle(tmp_path):
    """A standard file in its own directory, next to a KML file with two polygon layers and a point layer."""
    kml_path = tmp_path / "source.kml"
    kml_path.write_text(
        _kml_text(
            {
                "perimeter_a": [_polygon_placemark(SQUARE_A1), _polygon_placemark(SQUARE_A2)],
                "hot_spots": [_point_placemark(-120.45, 38.55), _point_placemark(-120.35, 38.65)],
                "perimeter_b": [_polygon_placemark(SQUARE_B)],
            }
        ),
        encoding="utf-8",
    )
    h5_dir = tmp_path / "bundle"
    h5 = fs.new_std_file(str(h5_dir / "perimeters.h5"), "FireBench tests")
    yield h5, h5_dir, kml_path
    h5.close()


def test_list_kml_layers_gives_names_in_order_and_polygon_counts(bundle):
    _, _, kml_path = bundle

    layers = fs.list_kml_layers(kml_path)

    # GDAL may also list the enclosing document as a layer of its own
    counts = {layer["name"]: layer["n_polygons"] for layer in layers}
    names = [
        layer["name"] for layer in layers if layer["name"] in ("perimeter_a", "hot_spots", "perimeter_b")
    ]
    assert names == ["perimeter_a", "hot_spots", "perimeter_b"]
    assert counts["perimeter_a"] == 2
    assert counts["hot_spots"] == 0
    assert counts["perimeter_b"] == 1
    assert all(count == 0 for name, count in counts.items() if name not in names)


@pytest.mark.parametrize("content", [None, "this is not KML"])
def test_list_kml_layers_refuses_unreadable_file(tmp_path, content):
    kml_path = tmp_path / "broken.kml"
    if content is not None:
        kml_path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="broken.kml"):
        fs.list_kml_layers(kml_path)


def test_list_kml_layers_refuses_other_file_types(tmp_path):
    path = tmp_path / "perimeter.geojson"
    path.write_text("{}", encoding="utf-8")
    not_a_zip = tmp_path / "perimeter.kmz"
    not_a_zip.write_text("this is not a ZIP archive", encoding="utf-8")
    empty_kmz = tmp_path / "empty.kmz"
    with zipfile.ZipFile(empty_kmz, "w") as archive:
        archive.writestr("readme.txt", "no KML here")

    with pytest.raises(ValueError, match="not a .kml or .kmz file"):
        fs.list_kml_layers(path)
    with pytest.raises(ValueError, match="not a ZIP archive"):
        fs.list_kml_layers(not_a_zip)
    with pytest.raises(ValueError, match="holds no KML file"):
        fs.list_kml_layers(empty_kmz)


def test_chosen_layer_is_the_one_stored(bundle):
    h5, h5_dir, kml_path = bundle

    group = fs.standardize_perimeter_from_kml(
        kml_path, h5, "Test_B", TIME, h5_dir / "kml", layer="perimeter_b"
    )

    stored = gpd.read_file(h5_dir / group.attrs["rel_path"])
    assert len(stored) == 1
    assert _stored_polygons(group, h5_dir).equals(Polygon(SQUARE_B))
    assert [layer["name"] for layer in fs.list_kml_layers(h5_dir / group.attrs["rel_path"])] == [
        "fire_perimeter"
    ]


@pytest.mark.parametrize("area_crs", [None, "EPSG:3310"])
def test_known_square_gives_its_area_in_acres(tmp_path, area_crs):
    # a 1 km square, built in an equal-area projection centred on it so its true area is 1 km2
    local = "+proj=laea +lat_0=38.75 +lon_0=-120.25 +datum=WGS84 +units=m"
    to_lonlat = Transformer.from_crs(local, "EPSG:4326", always_xy=True)
    corners = [(-500, -500), (500, -500), (500, 500), (-500, 500), (-500, -500)]
    kml_path = tmp_path / "square.kml"
    kml_path.write_text(
        _kml_text({"square": [_polygon_placemark([to_lonlat.transform(x, y) for x, y in corners])]}),
        encoding="utf-8",
    )

    with fs.new_std_file(str(tmp_path / "bundle" / "square.h5"), "FireBench tests") as h5:
        group = fs.standardize_perimeter_from_kml(
            kml_path, h5, "square", TIME, tmp_path / "bundle" / "kml", layer="square", area_crs=area_crs
        )

        assert group.attrs["burnt_area"] == pytest.approx(1e6 / ACRE_IN_M2, rel=1e-3)
        assert group.attrs["burnt_area_units"] == "acre"


@pytest.mark.parametrize("area_crs", ["EPSG:4326", "EPSG:2227"])
def test_area_projection_must_be_projected_in_metres(bundle, area_crs):
    h5, h5_dir, kml_path = bundle

    with pytest.raises(ValueError, match="projected CRS in metres"):
        fs.standardize_perimeter_from_kml(
            kml_path, h5, "Test", TIME, h5_dir / "kml", layer="perimeter_b", area_crs=area_crs
        )

    assert not (h5_dir / "kml").exists()


def test_group_attributes_and_referenced_file(bundle):
    h5, h5_dir, kml_path = bundle
    group_name = f"Test_{TIME}"

    group = fs.standardize_perimeter_from_kml(
        kml_path, h5, group_name, TIME, h5_dir / "kml", layer="perimeter_a"
    )

    kml_file = h5_dir / "kml" / "Test_2021_08_17T20_20_07_00.kml"
    assert group.name == f"/polygons/{group_name}"
    assert set(group.attrs) == {
        "rel_path",
        "sha256",
        "file_size_bytes",
        "time",
        "burnt_area",
        "burnt_area_units",
    }
    assert group.attrs["rel_path"] == "kml/Test_2021_08_17T20_20_07_00.kml"
    assert group.attrs["sha256"] == hashlib.sha256(kml_file.read_bytes()).hexdigest()
    assert group.attrs["file_size_bytes"] == kml_file.stat().st_size
    assert group.attrs["time"] == TIME
    assert group.attrs["burnt_area"] > 0
    assert group.attrs["burnt_area_units"] == "acre"
    assert fs.validate_h5_referenced_files(h5) == (True, None)


def test_only_layer_is_read_without_a_name(bundle):
    h5, h5_dir, kml_path = bundle
    first = fs.standardize_perimeter_from_kml(
        kml_path, h5, "first", TIME, h5_dir / "kml", layer="perimeter_b"
    )

    # the file the function writes has one layer
    second = fs.standardize_perimeter_from_kml(
        h5_dir / first.attrs["rel_path"], h5, "second", TIME, h5_dir / "kml"
    )

    assert _stored_polygons(second, h5_dir).equals(Polygon(SQUARE_B))
    assert second.attrs["burnt_area"] == pytest.approx(first.attrs["burnt_area"])


@pytest.mark.parametrize(
    "arguments,message",
    [
        ({"layer": "no_such_layer"}, "layer 'no_such_layer' not found"),
        ({"layer": None}, "Name one with `layer`"),
        ({"layer": "hot_spots"}, "holds no polygon"),
        ({"time": "2021-08-17T20:20"}, "UTC offset"),
        ({"time": "17 August 2021"}, "UTC offset"),
        ({"group_name": "a/b"}, "must not be empty or contain '/'"),
    ],
)
def test_refusals_write_nothing(bundle, arguments, message):
    h5, h5_dir, kml_path = bundle
    arguments = {"group_name": "Test", "time": TIME, "layer": "perimeter_b", **arguments}

    with pytest.raises(ValueError, match=message):
        fs.standardize_perimeter_from_kml(kml_path, h5, kml_dir=h5_dir / "kml", **arguments)

    assert "polygons" not in h5
    assert not (h5_dir / "kml").exists()


def test_refusal_lists_layers_with_polygon_counts(bundle):
    h5, h5_dir, kml_path = bundle

    with pytest.raises(ValueError) as error:
        fs.standardize_perimeter_from_kml(kml_path, h5, "Test", TIME, h5_dir / "kml")

    assert "'perimeter_a' (2 polygons)" in str(error.value)
    assert "'hot_spots' (0 polygons)" in str(error.value)


def test_kml_dir_outside_the_file_directory_is_refused(bundle, tmp_path):
    h5, _, kml_path = bundle

    with pytest.raises(ValueError, match="must be inside the directory of the HDF5 file"):
        fs.standardize_perimeter_from_kml(
            kml_path, h5, "Test", TIME, tmp_path / "elsewhere", layer="perimeter_b"
        )

    assert not (tmp_path / "elsewhere").exists()


def test_existing_group_is_refused_without_overwrite(bundle):
    h5, h5_dir, kml_path = bundle
    fs.standardize_perimeter_from_kml(kml_path, h5, "Test", TIME, h5_dir / "kml", layer="perimeter_a")
    sha256 = h5["polygons/Test"].attrs["sha256"]

    with pytest.raises(ValueError, match="already exists"):
        fs.standardize_perimeter_from_kml(kml_path, h5, "Test", TIME, h5_dir / "kml", layer="perimeter_b")
    assert h5["polygons/Test"].attrs["sha256"] == sha256

    group = fs.standardize_perimeter_from_kml(
        kml_path, h5, "Test", TIME, h5_dir / "kml", layer="perimeter_b", overwrite=True
    )
    assert _stored_polygons(group, h5_dir).equals(Polygon(SQUARE_B))
    assert fs.validate_h5_referenced_files(h5) == (True, None)


def test_group_names_that_give_the_same_file_name_are_refused(bundle):
    h5, h5_dir, kml_path = bundle
    fs.standardize_perimeter_from_kml(kml_path, h5, "Test-1", TIME, h5_dir / "kml", layer="perimeter_a")

    with pytest.raises(ValueError, match="gives the same KML file name"):
        fs.standardize_perimeter_from_kml(kml_path, h5, "Test:1", TIME, h5_dir / "kml", layer="perimeter_b")

    assert fs.validate_h5_referenced_files(h5) == (True, None)


def test_kmz_gives_the_same_polygons_as_its_kml(bundle, tmp_path):
    h5, h5_dir, kml_path = bundle
    kmz_path = tmp_path / "source.kmz"
    with zipfile.ZipFile(kmz_path, "w") as archive:
        archive.write(kml_path, "doc.kml")

    assert fs.list_kml_layers(kmz_path) == fs.list_kml_layers(kml_path)

    from_kml = fs.standardize_perimeter_from_kml(
        kml_path, h5, "from_kml", TIME, h5_dir / "kml", layer="perimeter_a"
    )
    from_kmz = fs.standardize_perimeter_from_kml(
        kmz_path, h5, "from_kmz", TIME, h5_dir / "kml", layer="perimeter_a"
    )

    assert _stored_polygons(from_kmz, h5_dir).equals(_stored_polygons(from_kml, h5_dir))
    assert from_kmz.attrs["burnt_area"] == from_kml.attrs["burnt_area"]


def test_every_ring_of_an_inner_boundary_is_kept_as_a_hole(tmp_path):
    expected = Polygon(SQUARE_B, [HOLE_1, HOLE_2])
    # the same polygon with its two holes, in standard KML and with both rings in one inner boundary
    inner_boundaries = {"standard": [[HOLE_1], [HOLE_2]], "several_rings": [[HOLE_1, HOLE_2]]}

    with fs.new_std_file(str(tmp_path / "bundle" / "holes.h5"), "FireBench tests") as h5:
        groups = {}
        for name, boundaries in inner_boundaries.items():
            kml_path = tmp_path / f"{name}.kml"
            kml_path.write_text(
                _kml_text({"perimeter": [_polygon_placemark(SQUARE_B, boundaries)]}), encoding="utf-8"
            )
            groups[name] = fs.standardize_perimeter_from_kml(
                kml_path,
                h5,
                name,
                TIME,
                tmp_path / "bundle" / "kml",
                layer="perimeter",
                area_crs="EPSG:3310",
            )
            stored = _stored_polygons(groups[name], tmp_path / "bundle")
            assert shapely.get_num_interior_rings(shapely.get_parts(stored)).sum() == 2
            assert stored.equals(expected)

        area = gpd.GeoSeries([expected], crs="EPSG:4326").to_crs("EPSG:3310").area.sum() / ACRE_IN_M2
        assert groups["several_rings"].attrs["burnt_area"] == pytest.approx(area, rel=1e-9)
        assert groups["several_rings"].attrs["burnt_area"] == groups["standard"].attrs["burnt_area"]


def test_overwrite_writes_the_file_a_first_write_gives(bundle):
    h5, h5_dir, kml_path = bundle
    first = fs.standardize_perimeter_from_kml(
        kml_path, h5, "first", TIME, h5_dir / "kml", layer="perimeter_b"
    )
    fs.standardize_perimeter_from_kml(kml_path, h5, "again", TIME, h5_dir / "kml", layer="perimeter_a")

    again = fs.standardize_perimeter_from_kml(
        kml_path, h5, "again", TIME, h5_dir / "kml", layer="perimeter_b", overwrite=True
    )

    assert again.attrs["sha256"] == first.attrs["sha256"]
    assert sorted(path.name for path in (h5_dir / "kml").iterdir()) == ["again.kml", "first.kml"]


def test_failed_write_leaves_the_previous_file_and_group(bundle, monkeypatch):
    h5, h5_dir, kml_path = bundle
    fs.standardize_perimeter_from_kml(kml_path, h5, "Test", TIME, h5_dir / "kml", layer="perimeter_a")
    sha256 = h5["polygons/Test"].attrs["sha256"]

    def fail_after_writing(_perimeter, path, **_arguments):
        path.write_text("half a file", encoding="utf-8")
        raise RuntimeError("disk full")

    monkeypatch.setattr(gpd.GeoDataFrame, "to_file", fail_after_writing)
    with pytest.raises(RuntimeError, match="disk full"):
        fs.standardize_perimeter_from_kml(
            kml_path, h5, "Test", TIME, h5_dir / "kml", layer="perimeter_b", overwrite=True
        )

    assert h5["polygons/Test"].attrs["sha256"] == sha256
    assert [path.name for path in (h5_dir / "kml").iterdir()] == ["Test.kml"]
    assert fs.validate_h5_referenced_files(h5) == (True, None)
