"""
Parsing of wgrib2-style GRIB2 ``.idx`` inventories and selection of messages by ``VAR:LEVEL``.

The selected messages drive byte-range subset downloads. Ported from spear ``backends/hrrr/inventory``
and hardened for sub-message numbering (``600.1``), for messages sharing a byte offset, and for
fields that exist both as instantaneous values and as time statistics (``0-1 hour max fcst``).
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

INSTANTANEOUS_FORECAST = re.compile(r"^(anl|\d+ hour fcst)$")


@dataclass(frozen=True)
class GribMessage:
    """One inventory line: byte range (inclusive) and ``VAR``/``LEVEL``/forecast descriptors."""

    number: str
    byte_start: int
    byte_end: int | None  # inclusive; None = until end of file (last message)
    var: str
    level: str
    forecast: str

    @property
    def field(self) -> str:
        """``VAR:LEVEL`` name, e.g. ``TMP:2 m above ground``."""
        return f"{self.var}:{self.level}"

    @property
    def instantaneous(self) -> bool:
        """Whether the message is an analysis or an instantaneous forecast (not a max/mean/accum)."""
        return bool(INSTANTANEOUS_FORECAST.match(self.forecast))


def parse_index(text: str) -> list[GribMessage]:
    """
    Parse a wgrib2-style ``.idx`` file, e.g. ``71:43912124:d=2021082000:TMP:2 m above ground:1 hour fcst:``.

    A message ends one byte before the next *larger* offset, so sub-messages that share an offset
    (``600:...`` and ``600.2:...``) get the same range instead of an inverted one.
    """
    raw = []
    for line in text.splitlines():
        parts = line.split(":")
        if len(parts) < 6 or not parts[1].strip().isdigit():
            continue
        raw.append((parts[0].strip(), int(parts[1]), parts[3], parts[4], parts[5]))

    offsets = sorted({start for _, start, *_ in raw})
    next_offset = dict(zip(offsets, offsets[1:]))
    return [
        GribMessage(
            number=number,
            byte_start=start,
            byte_end=next_offset[start] - 1 if start in next_offset else None,
            var=var,
            level=level,
            forecast=forecast,
        )
        for number, start, var, level, forecast in raw
    ]


def select_messages(
    messages: list[GribMessage], fields: list[str] | tuple[str, ...], *, instantaneous: bool = True
) -> list[GribMessage]:
    """
    Select the messages matching the requested ``VAR:LEVEL`` fields, in byte order.

    With ``instantaneous=True`` only analyses and instantaneous forecasts qualify, so
    ``WIND:10 m above ground:0-1 hour max fcst`` is never mistaken for an instantaneous wind.
    Raises ``ValueError`` if a field is missing or if two fields share one GRIB message.
    """
    by_field: dict[str, list[GribMessage]] = {}
    for message in messages:
        if instantaneous and not message.instantaneous:
            continue
        by_field.setdefault(message.field, []).append(message)

    missing = [field for field in fields if field not in by_field]
    if missing:
        raise ValueError(f"fields not found in GRIB inventory: {missing}")

    selected = []
    for field in fields:
        matches = by_field[field]
        if len(matches) > 1:
            logger.debug("[hrrr] field %s matches %d messages, keeping the first", field, len(matches))
        selected.append(matches[0])

    starts = [message.byte_start for message in selected]
    if len(set(starts)) != len(starts):
        raise ValueError(f"requested fields share a GRIB message and cannot be subset separately: {fields}")
    return sorted(selected, key=lambda message: message.byte_start)
