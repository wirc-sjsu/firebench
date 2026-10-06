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

### Tokens with HTTP Origin restrictions

For Synoptic tokens with HTTP Origin restrictions, answer **Yes** when `keys set synoptic`
asks whether the token has restrictions. Enter each concrete allowed origin, including its
`http://` or `https://` scheme and port if applicable, then enter an empty line to finish.
For example, enter `https://first.example` and `https://second.example` on separate lines.
Use values already allowed by your token in the
[Synoptic customer console](https://customer.synopticdata.com/). FireBench records these values
locally; it does not change the allowed origins on Synoptic. A free token can use this feature,
but an Origin header does not grant access to services your account lacks.

To add both origins to a token you have already stored, without re-entering it:

```bash
firebench keys origins add synoptic https://first.example https://second.example
firebench keys origins list synoptic
firebench keys check synoptic --online
```

Remove an origin with:

```bash
firebench keys origins remove synoptic https://first.example
```

For scripted setup, repeat `--origin`; with `--stdin`, the command reads the token's first
line and never prompts for origins:

```bash
< ~/secrets/synoptic.txt firebench keys set synoptic --stdin --origin https://first.example --origin https://second.example
```

Origins are stored in a private `synoptic.origins.json` sidecar beside the token and bound to
its full SHA-256 hash. Re-saving the same token preserves its origins unless you supply replacement
origins. Replacing or removing the token clears its old origin metadata. Tokens from an environment
variable or explicit file use saved origins only if they match the stored token exactly.

Each request sends one Origin header. FireBench tries saved origins in order, advancing only after
an HTTP or API 403. It reuses the successful origin first for subsequent requests in that client.
If all fail, the error lists attempted origins. It never retries without an Origin header.
Requests with no configured origins omit the header.

To select one origin explicitly:

```bash
firebench keys check synoptic --online --origin https://second.example
```

Or use an environment override for token checks and weather downloads:

```bash
export SYNOPTIC_ORIGIN='https://second.example'
```

A weather setup can override both the environment and saved list:

```yaml
observations:
  origin: https://second.example
```

Precedence is explicit `--origin` / `observations.origin`, then `SYNOPTIC_ORIGIN`, then the token's
saved origins. An override uses only that origin. `firebench wx plan` shows the effective list and
its source. Changing the effective list invalidates acquisition cache and workflow identities.
Origins must be concrete HTTP(S) URLs with a hostname and optional port, without credentials,
paths, queries, fragments, whitespace, or wildcards. A trailing slash is normalized away.

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
| `HTTP 403` or `attempted origins: ...` | Check the saved origins against the token’s Synoptic settings and verify Weather API access; a matching Origin cannot grant missing account access |
| `invalid Synoptic origin metadata` | Remove the sidecar named in the error, then re-add your origins |
| `Querying too many station hours` | The request exceeded the station-hour cap; lower `observations.max_chunk_days` |
| `no weather station with observations in the domain and window` | Widen the box or check the dates |
| `dropped station ...: missing ...` (log) | Synoptic returned a station without metadata the standardizer needs; it is skipped and reported |
