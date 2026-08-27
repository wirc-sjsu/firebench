from copy import deepcopy
import json

import h5py
import pytest

from firebench import standardize as fs

PROVENANCE = {
    "source_reference": "https://example.test/sensor-height-evidence",
    "source_date": "2026-07-01",
    "verification_date": "2026-07-24",
    "reviewer_or_authority": "Test reviewer",
    "notes": "Test evidence.",
}


def _record(
    record_id,
    *,
    record_type="station-specific",
    station="TEST",
    provider="Test provider",
    variable="wind_speed_set_1",
    height=10.0,
    confidence=2,
    status="active",
):
    record = {
        "record_id": record_id,
        "provider": provider,
        "variables": [variable],
        "height": height,
        "units": "m",
        "confidence": confidence,
        "status": status,
    }
    if record_type != "provider-default":
        record["station"] = station
    return record


def _document(record_type="station-specific", records=None):
    if records is None:
        records = [_record("test-record", record_type=record_type)]
    return {
        "schema_version": 1,
        "record_type": record_type,
        "provenance": deepcopy(PROVENANCE),
        "records": records,
    }


def _expanded_resources(station_records=(), history_records=(), provider_records=()):
    return fs.SensorHeightResources(
        station_specific=fs.validate_sensor_height_resource(
            _document("station-specific", list(station_records)),
        ),
        historical=fs.validate_sensor_height_resource(
            _document("historical", list(history_records)),
        ),
        provider_default=fs.validate_sensor_height_resource(
            _document("provider-default", list(provider_records)),
        ),
    )


def test_installed_sensor_height_resources_are_versioned_and_valid():
    assert fs.validate_installed_sensor_height_resources() == {
        "station-specific": 4788,
        "historical": 81,
        "provider-default": 16,
    }


def test_every_installed_trusted_record_has_traceable_provenance():
    resources = fs.load_sensor_height_resources()
    trusted_records = (*resources.station_specific, *resources.historical)

    assert trusted_records
    for record in trusted_records:
        assert record.confidence is fs.SensorHeightConfidence.VERIFIED
        assert record.source_reference
        assert record.verification_date
        assert record.reviewer_or_authority
        assert record.record_id


@pytest.mark.parametrize(
    ("station", "variable", "provider", "height", "source"),
    (
        (
            "000PG",
            "wind_speed_set_1",
            "Western Weather Group",
            7.9,
            "firebench_trusted_stations",
        ),
        (
            "BDMC1",
            "air_temp_set_1",
            "Bureau of Land Management",
            2.0,
            "firebench_trusted_history",
        ),
        (
            "NO_RECORD",
            "wind_speed_set_1",
            "Bureau of Land Management",
            6.1,
            "firebench_providers_default",
        ),
    ),
)
def test_migrated_resources_preserve_known_resolutions(
    station,
    variable,
    provider,
    height,
    source,
):
    resolution = fs.resolve_sensor_height(
        station=station,
        variable=variable,
        provider=provider,
        verification_date="2026-07-24",
    )

    assert resolution.height == height
    assert resolution.source == source


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda document: document.update({"schema_version": 2}), "schema_version"),
        (lambda document: document["records"].append(deepcopy(document["records"][0])), "record_id"),
        (
            lambda document: document["records"][0].update(
                {"record_id": "second", "variables": ["unsupported_set_1"]}
            ),
            "unsupported",
        ),
        (lambda document: document["records"][0].update({"height": -1}), "height"),
        (lambda document: document.pop("provenance"), "provenance"),
        (lambda document: document["records"][0].update({"confidence": 9}), "confidence"),
    ),
)
def test_sensor_height_resource_validation_rejects_invalid_records(mutation, message):
    document = _document()
    mutation(document)

    with pytest.raises(ValueError, match=message):
        fs.validate_sensor_height_resource(document)


def test_sensor_height_resource_validation_rejects_duplicate_selectors():
    first = _record("first")
    second = _record("second")

    with pytest.raises(ValueError, match="Duplicate active/proposed"):
        fs.validate_sensor_height_resource(_document(records=[first, second]))


def test_sensor_height_resolver_applies_source_precedence():
    resources = _expanded_resources(
        station_records=[_record("station", height=8.0)],
        history_records=[_record("history", height=9.0)],
        provider_records=[
            _record(
                "provider",
                record_type="provider-default",
                height=10.0,
                confidence=1,
            )
        ],
    )

    station = fs.resolve_sensor_height(
        station="TEST",
        variable="wind_speed_set_1",
        provider="Test provider",
        verification_date="2026-07-24",
        resources=resources,
    )
    synoptic = fs.resolve_sensor_height(
        station="TEST",
        variable="wind_speed_set_1",
        provider="Test provider",
        synoptic_height=7.0,
        synoptic_source_reference="source.json#sha256=abc",
        verification_date="2026-07-24",
        resources=resources,
    )

    assert (station.height, station.source, int(station.confidence)) == (
        8.0,
        "firebench_trusted_stations",
        2,
    )
    assert (synoptic.height, synoptic.source, int(synoptic.confidence)) == (7.0, "from_data", 2)


def test_sensor_height_resolver_skips_revoked_records_and_uses_fallbacks():
    resources = _expanded_resources(
        station_records=[_record("station", height=8.0, status="revoked")],
        history_records=[_record("history", height=9.0, status="superseded")],
        provider_records=[
            _record(
                "provider",
                record_type="provider-default",
                height=6.1,
                confidence=1,
            )
        ],
    )

    provider = fs.resolve_sensor_height(
        station="TEST",
        variable="wind_speed_set_1",
        provider="Test provider",
        verification_date="2026-07-24",
        resources=resources,
    )
    fallback = fs.resolve_sensor_height(
        station="OTHER",
        variable="wind_speed_set_1",
        provider="Other provider",
        verification_date="2026-07-24",
        resources=resources,
    )

    assert (provider.height, provider.source, int(provider.confidence)) == (
        6.1,
        "firebench_providers_default",
        1,
    )
    assert (fallback.height, fallback.source, int(fallback.confidence)) == (
        10.0,
        "firebench_default",
        0,
    )


def _synoptic_source():
    return {
        "STATION": [
            {
                "STID": "TEST",
                "NAME": "Test station",
                "ID": "1",
                "MNET_ID": "2",
                "STATE": "CA",
                "TIMEZONE": "UTC",
                "LATITUDE": "38.0",
                "LONGITUDE": "-120.0",
                "ELEVATION": "1000",
                "UNITS": {"elevation": "ft"},
                "PROVIDERS": [{"name": "Test provider"}],
                "OBSERVATIONS": {
                    "date_time": ["2026-07-24T00:00:00Z"],
                    "wind_speed_set_1": [3.0],
                },
                "SENSOR_VARIABLES": {
                    "wind": {
                        "wind_speed_set_1": {
                            "position": 7.5,
                        }
                    }
                },
            }
        ]
    }


def test_synoptic_standardization_preserves_height_source_provenance(tmp_path):
    source_path = tmp_path / "synoptic.json"
    source_path.write_text(json.dumps(_synoptic_source()), encoding="utf-8")
    output_path = tmp_path / "weather.h5"

    with h5py.File(output_path, "w") as output:
        fs.standardize_synoptic_raws_from_json(source_path, output)

    with h5py.File(output_path, "r") as output:
        variable = output["time_series/station_TEST/wind_speed"]
        source_hash = output["time_series/station_TEST"].attrs["source_file_sha256"]
        assert variable.attrs["sensor_height"] == 7.5
        assert variable.attrs["sensor_height_source"] == "from_data"
        assert variable.attrs["sensor_height_provider"] == "Test provider"
        assert variable.attrs["sensor_height_source_reference"] == (f"synoptic.json#sha256={source_hash}")
        assert variable.attrs["sensor_height_reviewer_or_authority"] == "Synoptic Data PBC"


def test_synoptic_history_export_creates_auditable_proposal(tmp_path):
    source_path = tmp_path / "synoptic.json"
    source_path.write_text(json.dumps(_synoptic_source()), encoding="utf-8")
    proposal_path = tmp_path / "proposal.json"

    count = fs.export_synoptic_sensor_height_proposal(
        source_path,
        proposal_path,
        source_date="2026-07-23",
        verification_date="2026-07-24",
        reviewer_or_authority="Test reviewer",
    )
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    records = fs.validate_sensor_height_resource(proposal, expected_type="historical")

    assert count == 1
    assert len(records) == 1
    assert records[0].status == "proposed"
    assert records[0].height == 7.5
    assert "sha256=" in records[0].source_reference
