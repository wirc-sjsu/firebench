# Generate Plots from TOML

Start from the complete [plot configuration](../examples/plot.toml) and keep paths relative to the
TOML file. Each `[[files]]` table needs an existing HDF5 `path`; `label` and `color` control the
legend. Global `output_dir` and `dpi` control generated PNGs.

The currently supported `[perimeter]` plot finds polygon datasets common to all inputs. Restrict
them with `paths`, change the search root with `group`, and control `projection`, `alpha`,
`fill_alpha`, `linewidth`, and `figsize`. Set `satellite = false` for offline or reproducible builds;
when enabled, `basemap_source` names a Contextily provider and requires network access.

```bash
firebench plot plot.toml
```

If no image is written, verify that all files expose the same polygon HDF5 paths and that each
dataset's `rel_path` resolves relative to its HDF5 file.
