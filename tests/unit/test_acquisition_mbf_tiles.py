"""Microsoft building footprints by box: quadkeys, index, cache, clip."""

import gzip
import json

import pytest

from firebench.acquisition import mbf_tiles
from firebench.acquisition.mbf_tiles import fetch_mbf_footprints, quadkeys_for_bbox


def _feature(lon, lat, size=0.001):
    ring = [[lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat]]
    return json.dumps(
        {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}
    )


class _Response:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        return self.data

    status = 200
    headers = {}

    def getcode(self):
        return 200


def _opener(files, calls):
    def opener(request, timeout=None):
        url = getattr(request, "full_url", request)
        calls.append(url)
        return _Response(files[url])

    return opener


def test_creek_and_caldor_boxes_give_their_zoom_9_tiles():
    assert quadkeys_for_bbox((-119.21, 37.19, -119.19, 37.21)) == ["023010330"]
    assert quadkeys_for_bbox((-120.41, 38.89, -120.39, 38.91)) == ["023010122"]


def test_a_box_over_two_tiles_gives_both():
    keys = quadkeys_for_bbox((-119.3, 37.19, -118.0, 37.21))
    assert len(keys) > 1 and "023010330" in keys


def test_an_invalid_box_is_refused():
    with pytest.raises(ValueError, match="invalid box"):
        quadkeys_for_bbox((-119.1, 37.1, -119.3, 37.3))


def test_local_dir_gives_the_footprints_inside_the_box(tmp_path):
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    (tiles / "023010330.geojsonl").write_text(_feature(-119.2, 37.2) + "\n" + _feature(-100.0, 10.0) + "\n")
    out = fetch_mbf_footprints((-119.21, 37.19, -119.19, 37.21), tmp_path / "out.geojsonl", local_dir=tiles)
    assert out.n_footprints == 1
    assert len(out.path.read_text().splitlines()) == 1
    assert [t.quadkey for t in out.tiles] == ["023010330"]


def test_a_box_with_no_tile_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no tile"):
        fetch_mbf_footprints((-119.21, 37.19, -119.19, 37.21), tmp_path / "o.geojsonl", local_dir=tmp_path)


def test_tiles_are_downloaded_once_and_kept(tmp_path):
    url = "https://example.test/023010330.csv.gz"
    index = f"Location,QuadKey,Url,Size,UploadDate\nUnitedStates,023010330,{url},1KB,2026-08-13\n".encode()
    tile = gzip.compress((_feature(-119.2, 37.2) + "\n").encode())
    calls = []
    opener = _opener({mbf_tiles.INDEX_URL: index, url: tile}, calls)
    box = (-119.21, 37.19, -119.19, 37.21)
    first = fetch_mbf_footprints(box, tmp_path / "a.geojsonl", cache_dir=tmp_path / "cache", opener=opener)
    second = fetch_mbf_footprints(box, tmp_path / "b.geojsonl", cache_dir=tmp_path / "cache", opener=opener)
    assert (first.n_footprints, second.n_footprints) == (1, 1)
    assert first.sha256 == second.sha256
    assert calls == [mbf_tiles.INDEX_URL, url]
    assert [t.cached for t in second.tiles] == [True]
