# Add or Update a Standard Variable Name

Search `src/firebench/tools/namespace.py` and [the namespace reference](../namespace.md) before
adding a synonym. Prefer an existing name when its scientific meaning and units match.

Add a descriptive `UPPER_CASE` constant to `StandardVariableNames`; its string value must be
lowercase snake case. Update the corresponding description and canonical units in
`docs/namespace.md`. Then run:

```bash
make check-consistency-namespace
```

Update converters and model metadata to use the constant instead of repeating strings. Add a test
when the name affects validation or an adapter, explain the scientific definition and expected
units in the pull request, and add a changelog entry for a user-visible namespace change.
