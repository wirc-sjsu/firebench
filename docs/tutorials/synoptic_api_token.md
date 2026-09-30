# Download Synoptic Observations with an API Token

The automated weather benchmark (`firebench wx`) downloads weather-station observations from the
[Synoptic Data](https://synopticdata.com) weather API. That requires a personal API token. This
tutorial stores the token safely, checks it, and runs a small end-to-end test on a small domain.

## 1. Get a token

Create an account on the [Synoptic customer console](https://customer.synopticdata.com/) and
generate an API token. Open-access accounts may limit how far back historical data are available,
which is why the test below uses a recent window.

## 2. Store the token

```bash
firebench keys set synoptic
```

The token is prompted twice with hidden input and stored in
`~/.config/firebench/credentials/synoptic`, readable by you only (mode `0600`). FireBench never
prints a token; it shows a fingerprint (its length and a short SHA-256 prefix) instead.

FireBench looks for the token in this order:

1. the file named by `observations.token_file` in a setup (an error if that file does not exist);
2. the `SYNOPTIC_TOKEN` environment variable;
3. the key stored by `firebench keys set`.

Never write a token in a setup file, because setup files get shared. FireBench refuses such a
setup.

## 3. Check the token

```bash
firebench keys check synoptic --online
```

The command shows where the token was found and sends one tiny request to Synoptic to confirm it
is accepted. List every key known to FireBench with:

```bash
firebench keys list
```

## 4. Run a small domain

Create a setup for a small box and a recent two-day window with one 00Z forecast cycle. Edit the
dates so that the window ends a few days before today:

```bash
firebench wx init small_bbox.yml --bbox=-120.8,38.6,-120.4,38.9 --start 2026-09-25T00:00Z --end 2026-09-27T00:00Z
firebench wx plan small_bbox.yml
firebench wx run small_bbox.yml
```

`plan` makes no request: it shows the Synoptic request and which key would be used. `run` counts
the stations of the request first. Synoptic caps each request at 100,000 station-hours, so
FireBench splits long windows into chunks and merges them. Finished chunks are cached; recent
chunks are fetched again because late observations keep arriving.

## 5. Validation checklist

When a live token is used for the first time, check these points and report anything unexpected:

1. `firebench keys check synoptic --online` reports `online check: OK`.
2. `firebench wx run small_bbox.yml` downloads the payload. `runs/small_bbox/observations/synoptic.json`
   parses, and `obs.h5` holds the stations of the box.
3. With `max_chunk_days: 0.5` under `observations` (which forces several chunks), and a new
   `output_dir`, the run gives the same station set and record counts as a single-chunk run.
4. A wrong token (for example `SYNOPTIC_TOKEN=wrong firebench wx run ...`) gives Synoptic's error
   message, not a traceback. The token appears in no log line (`wx_workflow.log`) and no cache file.
5. Acceptance: re-download the Caldor weather window with the Caldor H012 preset, without
   `synoptic_json`. Compare the station set and record counts with the run from the saved Caldor
   JSON (see [Benchmark HRRR forecasts against weather stations](wx_hrrr_benchmark.md)) and explain
   any difference.

## Troubleshooting

| Message | Meaning |
|---|---|
| `No API key found for 'synoptic'` | No token in the lookup order above; run `firebench keys set synoptic` |
| `Synoptic API error 2: Invalid token. (HTTP 401)` | The token is wrong or expired |
| `Querying too many station hours` | The request exceeded the station-hour cap; lower `observations.max_chunk_days` |
| `no weather station with observations in the domain and window` | Widen the box or check the dates |
| `dropped station ...: missing ...` (log) | Synoptic returned a station without metadata the standardizer needs; it is skipped and reported |
