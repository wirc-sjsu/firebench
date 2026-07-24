# Curate Weather Sensor Heights

FireBench keeps station-specific, historical, and provider-default sensor heights as installed JSON
resources under `src/firebench/resources/`. These records affect which observations qualify for
Trusted Sources Only (TSO), so changes require evidence and review.

## Understand the versioned record format

All three files use schema version 1:

- `wx_sensor_height_stations.json` contains station-specific verified records.
- `wx_sensor_height_trusted_history.json` contains verified records recovered from earlier source
  metadata.
- `wx_sensor_height_providers.json` contains unverified provider-wide defaults.

Each document declares `schema_version`, `record_type`, shared `provenance`, and a `records` list.
A record can apply one height to several variables:

```json
{
  "schema_version": 1,
  "record_type": "station-specific",
  "provenance": {
    "source_reference": "https://example.org/stations/TEST",
    "source_date": "2026-07-01",
    "verification_date": "2026-07-24",
    "reviewer_or_authority": "Reviewer name or issuing authority",
    "notes": "Optional context about the evidence."
  },
  "records": [
    {
      "record_id": "station-test-wind-20260724",
      "station": "TEST",
      "provider": "Example provider",
      "variables": [
        "wind_direction_set_1",
        "wind_gust_set_1",
        "wind_speed_set_1"
      ],
      "height": 10.0,
      "units": "m",
      "confidence": 2,
      "status": "active"
    }
  ]
}
```

`height` is always a JSON number and `units` must describe a length accepted by Pint. A record may
override the document-level `provenance` object when its evidence differs. `source_date` may be
`null` only when the evidence has no recoverable publication or observation date. The source
reference, verification date, and reviewer or authority are required.

Station-specific and historical records use confidence 2. Provider-default records omit `station`
and use confidence 1. Supported statuses are:

- `proposed`: submitted for review and never selected by the resolver.
- `active`: eligible for source-precedence resolution.
- `superseded`: retained for the audit trail but no longer selected.
- `revoked`: rejected evidence retained for the audit trail and never selected.

The validator rejects unknown schema versions, duplicate record IDs, duplicate active or proposed
station/provider-variable selectors, unsupported variables, nonnumeric or negative heights,
non-length units, missing provenance, and invalid confidence or status values.

## Submit Synoptic metadata as evidence

Do not enable a hidden export while standardizing observations. Generate an explicit proposal at a
chosen path:

```python
from pathlib import Path

from firebench import standardize

standardize.export_synoptic_sensor_height_proposal(
    Path("synoptic_download.json"),
    Path("sensor_height_proposal.json"),
    source_date="2026-07-23",
    verification_date="2026-07-24",
    reviewer_or_authority="Your name or authority",
)
```

The proposal records the source filename and SHA-256, uses numeric heights and explicit units, and
leaves every record in `proposed` status. It does not modify an installed resource.

## Review and activate a record

1. Confirm that the source identifies the station, variable, height, units, and provider.
2. Check that the source reference is durable and that the source and verification dates are
   accurate. Retain the downloaded evidence outside the package when redistribution is not
   permitted.
3. Compare the proposal against all three resources and the documented
   [source precedence](../reference/weather_sensor_height.md#source-precedence).
4. Copy accepted records into the appropriate resource, give each a stable unique `record_id`, and
   change its status to `active`.
5. Run
   `python -c "from firebench.standardize import validate_installed_sensor_height_resources as v; print(v())"`
   and the focused resource tests.
6. Include the evidence, decision, affected stations and variables, and validation output in the
   pull-request description.

## Supersede or revoke evidence

Never silently replace or delete an accepted record. To correct it, change the old record to
`superseded`, add a new active record, and identify the old `record_id` in the new record's notes.
Use `revoked` when evidence is invalid and no replacement is accepted. Explain the reason in a
record-level provenance `notes` override. Inactive records remain validated and auditable but the
resolver ignores them.

Only one active or proposed record may select the same station/provider and variable within a
resource. Source precedence remains Synoptic metadata, station-specific records, historical
records, provider defaults, then FireBench variable defaults.
