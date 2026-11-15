# Score a model on an event catalogue

An event catalogue (see [Event catalogue](../standard_format.md#event-catalogue)) holds many fires in
one standard file. A **catalogue case** (schema `fb-catalogue-case-v1`) says which events a model is
scored on and how. A model is run once per fire, the outputs are put in one **bundle**, and
FireBench scores the bundle: one score card for the collection, with the median and spread of each
KPI across the events, and a table of every event's values.

```bash
firebench catalogue template catalogue.h5 templates/ --definition case.json
# run the model on each templates/<event_id>/template.h5, writing <event_id>/model.h5
firebench catalogue check case.json catalogue.h5 bundle/
firebench catalogue run case.json catalogue.h5 bundle/ -o card.json -r card.pdf -t events.csv
```

## The case

`case.json` is a canonical JSON document, named by its SHA-256 as `fb-case-v1` definitions are. It
holds no case or set ID, and no number that changes a score: those are in the parameter file
`event_catalogue.toml` that FireBench ships, which the definition names by `set` and `version`.

```json
{
  "schema": "fb-catalogue-case-v1",
  "name": "California 2017-2021, 1,000 acres or more",
  "parameters": {"set": "event_catalogue", "version": "2026.1"},
  "projection": "EPSG:5070",
  "event_ids_sha256": "...",
  "families": ["final_perimeter", "structure_loss"],
  "strata": ["size_class", "year"]
}
```

Propose one from the catalogue, and check it, in Python:

```python
from firebench.benchmarks.catalogue_case import check_catalogue_case, propose_catalogue_case

definition = propose_catalogue_case("catalogue.h5", "My case")
assert check_catalogue_case(definition, "catalogue.h5") == []
```

- `event_ids_sha256` is the SHA-256 of the sorted IDs joined by a line feed. It is the catalogue's
  own when the case scores every event. A subset is passed as a list of IDs (`event_ids=`, or
  `--event-ids FILE` with one ID per line), and the definition carries the hash of that list.
- `projection` is an equal-area projection the parameters allow (`EPSG:5070` or `EPSG:6933`).
  Areas, and so the size classes, are measured in it.
- `families` are `final_perimeter` and `structure_loss` (the second needs the catalogue's
  structures). `progression` and `area_growth` come in a later version of FireBench.
- `strata` are `size_class` (NWCG classes A to G of the observed area) and `year` (of the anchor
  time).

## Build a bundle

1. Write a template for each event. It is a standard file marked `firebench_template =
   "catalogue_event"` with the event's ignition point, a square box of `box_half_width_km` around
   it, and a window from the anchor time to the containment time (or `default_window_days` later).
   It has the group `/polygons/final_perimeter` with its `time` and no file, and, when the
   catalogue has structures for the event, the structures' positions in the group
   `/points/building_damaged` with a blank damage, except `Inaccessible`. It holds no observed
   perimeter. `firebench catalogue template CATALOGUE OUTDIR [--event ID]...` writes
   `<event_id>/template.h5` for each event; from Python, `write_event_template`.
2. Run the model on each template with its adapter. The model output is a new file, without the
   `firebench_template` attribute, that holds:
   - `/polygons/final_perimeter`, a group with the `rel_path`, `file_size_bytes` and `sha256` of a
     KML file of the model's final perimeter beside the output, and its `time`; a KML file with no
     polygon says the model burnt nothing, which is scored (Jaccard 0), not left out;
   - for `structure_loss`, `/points/building_damaged/building_damage`, one DINS damage label per
     structure, in the order of the template;
   - the model's attributes `model_name` and `model_version` on the root, the same in every file.
3. Put each event's files in a directory named exactly by its event ID, one `.h5` file per
   directory, and the directories in one bundle directory. If the outputs come as `<event_id>.zip`,
   unpack each into the directory of its ID.

```text
bundle/
  <event_id>/model.h5
  <event_id>/perimeter.kml
  ...
```

FireBench lists the directory; it never builds a path from an event ID.

## Check and run

`firebench catalogue check` prints a JSON report: the known, unknown, and missing event IDs, the
files that cannot be used with the reason, the model attributes, the families present, and the
coverage of each family: the events with an observation (`n_expected`), those the bundle gives a
usable result for (`n_given`), and whether their share reaches `min_coverage` (80 %).

`firebench catalogue run` refuses a bundle with an unknown ID, a stray file beside the event
directories, a directory with no or with more than one `.h5` file, a template submitted unchanged,
or model attributes that differ between events. A problem in one event's files (not a standard
file, an invalid or changed perimeter, a damage list of the wrong length) is not a refusal: its KPIs
are null with the reason in the table, and the coverage of its family drops. `--workers N` sets the
processes that score events (the CPU count by default); `--family` limits the families;
`--sign KEY SIGNER` certifies the card as `firebench case run` does.

## The collection score card

The result file has the header of an `fb-case-v1` score card (`case_schema`,
`case_definition_sha256`, `parameters`, `event_ids_sha256`, `evaluated_model_name`, `bundle_sha256`,
the catalogue's hash as `obs_dataset_hash`, certificates, `verification_lvl`), and the keys the
other cards have: `benchmarks`, `score_card` (`Scheme`, `Score <group>`, `Score Total`) and the PDF.

- Each KPI of a family has an ID (`G-FP01` Jaccard, `G-FP02` Dice-Sorensen, `G-FP03` relative area
  bias, `G-FP04` area ratio; `G-SL01` relative error of the lost structures). Its value in
  `benchmarks` is the **median** of the events' values and its `Score` the **median of the events'
  scores** (0 to 100 through the normalizations of the parameter file), not the score of the median.
- The score of a family is the mean of its KPI scores weighted by the parameter file, and the total
  the mean of the family scores weighted likewise. The total exists only when **every** chosen
  family reaches `min_coverage`; otherwise `score_card.no_total_reason` says which family and its
  coverage, and the KPIs of a family below coverage are left out of `benchmarks` and listed in
  `collection.omitted_kpis`.
- `collection` holds `n_events`, the SHA-256 of the per-event table, the `coverage` of each family,
  and for each KPI its `n_samples` and, for the values and for the scores, the `median`, the
  quartiles `q1` and `q3`, and the percentile bootstrap interval `ci_low` to `ci_high` of the median
  (`[statistics]` of the parameters: resamples, seed, confidence). With fewer than
  `min_samples_interval` samples the interval is null and `interval_reason` says so. `strata` holds
  the same, for each class of each stratum of the definition that has events.
- The per-event table is a CSV: `event_id, family, kpi_id, kpi_name, value, score, null_reason`,
  sorted, so the same bundle always gives the same bytes. A value FireBench did not compute is empty,
  with its reason.

The PDF holds the card and then, for each family, a table of each KPI's statistics and a box plot of
the events' scores.
