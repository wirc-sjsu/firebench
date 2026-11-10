import re
from pathlib import Path

from matplotlib import colormaps
from matplotlib.colors import to_hex
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from ..tools import logger
from ..signing import verify_certificate_in_dict, DEFAULT_VL, VERIFICATION_LEVEL_COLORS

SCORECARD_COLORS = {
    "header": "#1F3A5F",
    "subheader": "#3D6FA3",
    "group_row": "#D7E5C8",
    "row_even": "#F8F9FA",
    "row_odd": "#E8EDF3",
    "footer": "#7F8B99",
    "grid": "#9AA4AA",
    "body_text": "#1F2933",
    "low_score": "#8A8F98",
    "medium_score": "#4477AA",
    "high_score": "#228833",
    "invalid_score": "#595959",
}


# Shown wherever aggregation produced no score: a KPI was ignored (for example a weather KPI with
# no eligible station), so its group carries no weight and no score exists to display.
NOT_SCORED_TEXT = "n/a"

# How a one-page comparison chooses the KPIs it shows when more count than fit: the best and the
# worst by mean score across the models, or the largest differences between the models.
ONE_PAGE_RULES = ("extremes", "spread")

# Layout of the comparison score card, landscape A4. The drawing and the one-page selection share it.
COMPARISON_PAGE_SIZE = landscape(A4)
COMPARISON_MARGIN = 12 * mm
COMPARISON_HEADER_HEIGHT = 22 * mm
COMPARISON_ROW_HEIGHT = 7 * mm
COMPARISON_FOOTER_HEIGHT = 7 * mm


def comparison_rows_per_page() -> int:
    """Rows of one comparison page, the total score included."""
    usable = (
        COMPARISON_PAGE_SIZE[1]
        - 2 * COMPARISON_MARGIN
        - COMPARISON_HEADER_HEIGHT
        - COMPARISON_FOOTER_HEIGHT
    )
    return int(usable / COMPARISON_ROW_HEIGHT + 1e-9)


def _score_to_color(score):
    """
    Map a score from 0 to 100 to a colorblind-safer gray -> blue -> green scale.
    Output: hex string "#RRGGBB".
    """
    if score < 33.33:
        return SCORECARD_COLORS["low_score"]

    if score < 66.66:
        return SCORECARD_COLORS["medium_score"]

    return SCORECARD_COLORS["high_score"]


def _scorecard_benchmark_name(data: dict) -> str:
    return data.get("benchmark_short_name") or data.get("case_short_name") or data["case_id"]


def _scorecard_title(data: dict, scheme_name: str, verif_lvl: str, score: str) -> list[str]:
    return [
        f"Total Score {_scorecard_benchmark_name(data)} {scheme_name} for {data['evaluated_model_name']}",
        "",
        f"{verif_lvl}",
        score,
    ]


def _scorecard_footer(data: dict) -> str:
    footer = (
        f"FireBench version: {data['firebench_version']}   "
        f"Reference dataset version: {data['case_version']}"
    )
    if data.get("data_tier"):
        footer = f"{footer}   Data tier: {data['data_tier']}"
    return footer


def _scorecard_group_name(data: dict, group_name: str) -> str:
    """The group's display name, or its own name when another group of the score card shares that
    display name (FB001 names its five weather groups of a period "Weather Stations")."""
    names = data.get("score_card", {}).get("group_display_names", {})
    shown = names.get(group_name, group_name)
    if sum(1 for name in names.values() if name == shown) > 1:
        return group_name
    return shown


def _scorecard_kpi_name(bench_id: str, kpi_name: str, full_name: bool = False) -> str:
    if full_name:
        return f"{bench_id}: {kpi_name}"
    return re.sub(r"\s+(?:WH\d+|W\d+)$", "", kpi_name)


def _scorecard_comparison_rows(
    results: list[dict],
    include_kpis: bool = False,
    full_name: bool = False,
    groups: list[str] | None = None,
    kpis: dict[str, list[str]] | None = None,
) -> list[tuple[str, list[float]]]:
    """The total, then a row per group (``groups``, by default every group of the first result's
    scheme), each followed by its KPIs: those of ``kpis`` when given, else all with ``include_kpis``."""
    first_result = results[0]
    score_card = first_result.get("score_card")
    if score_card is None:
        raise ValueError("Comparison scorecard requires aggregated benchmark results")

    rows = [("Total Score", [result["score_card"].get("Score Total") for result in results])]
    for group_name in score_card["Scheme"].keys() if groups is None else groups:
        group_content = score_card["Scheme"][group_name]
        rows.append(
            (
                f"Group: {_scorecard_group_name(first_result, group_name)}",
                [result["score_card"].get(f"Score {group_name}") for result in results],
            )
        )
        if kpis is not None:
            bench_ids = kpis.get(group_name, [])
        elif include_kpis:
            bench_ids = list(group_content["benchmarks"].keys())
        else:
            bench_ids = []
        for bench_id in bench_ids:
            kpi_name = _comparison_kpi_name(results, bench_id)
            if kpi_name is None:
                # The KPI was ignored for every model, so no result carries a name or a score.
                continue
            rows.append(
                (
                    _scorecard_kpi_name(bench_id, kpi_name, full_name=full_name),
                    _comparison_kpi_scores(results, bench_id),
                )
            )
    return rows


def _comparison_kpi_scores(results: list[dict], bench_id: str) -> list[float | None]:
    return [result["benchmarks"].get(bench_id, {}).get("Score") for result in results]


def _counts(weight) -> bool:
    """Whether a weight of the scheme (a number, or a dict holding ``weight``) counts in the total."""
    if isinstance(weight, dict):
        weight = weight.get("weight", 0)
    return (weight or 0) > 0


def _rank(items: list[str], scores: dict[str, list[float]], rule: str, room: int) -> tuple[list[str], str]:
    """The ``room`` items of ``items`` a one-page rule keeps (ties keep the given order), and how."""
    if rule == "extremes":
        ranked = sorted(items, key=lambda item: sum(scores[item]) / len(scores[item]))
        half = room // 2
        return ranked[:half] + (ranked[-half:] if half else []), f"the {half} best and {half} worst"
    ranked = sorted(items, key=lambda item: min(scores[item]) - max(scores[item]))
    return ranked[:room], f"the {room} with the largest differences"


def _comparison_selection(
    results: list[dict], counted_only: bool = False, one_page: str | None = None, include_kpis: bool = False
) -> tuple[list[str], dict[str, list[str]] | None, str]:
    """The groups a comparison shows (score-card order), the KPIs under each (None: as
    ``include_kpis`` says), and a note for the header saying what was kept (empty: everything).

    ``counted_only`` keeps the groups and KPIs that count in the total: weight above 0 in the first
    result's scheme, which leaves out informational lead bins (the analysis and the ``(info)`` bins)
    and families shown for information.

    ``one_page`` (a rule of ``ONE_PAGE_RULES``) keeps what counts and fits on one page: the total and
    the groups that count, then their counted KPIs some model was scored on. When more KPIs count
    than fit, the rule picks them, each staying under its group:

    - ``"extremes"``: the x best and the x worst by mean score across the models;
    - ``"spread"``: the largest differences, the highest score less the lowest (0 for a KPI only one
      model was scored on).
    """
    if one_page is not None and one_page not in ONE_PAGE_RULES:
        raise ValueError(f"Unknown one-page rule {one_page!r}: expected one of {', '.join(ONE_PAGE_RULES)}")
    scheme = results[0]["score_card"]["Scheme"]
    if one_page is None and not counted_only:
        return list(scheme), None, ""
    groups = [group for group in scheme if _counts(scheme[group].get("weight", 0))]
    counted_kpis = {
        group: [
            bench_id
            for bench_id, weight in scheme[group]["benchmarks"].items()
            if _counts(weight) and _comparison_kpi_name(results, bench_id) is not None
        ]
        for group in groups
    }
    if one_page is None:
        return groups, counted_kpis if include_kpis else {}, "only what counts in the total"

    room = comparison_rows_per_page() - 1
    if len(groups) >= room:
        # More counted groups than rows: the rule picks groups, and no KPI fits.
        scores = {
            group: [
                score
                for score in (r["score_card"].get(f"Score {group}") for r in results)
                if score is not None
            ]
            or [0.0]
            for group in groups
        }
        chosen, how = _rank(groups, scores, one_page, room)
        kept = [group for group in groups if group in chosen]
        return kept, {}, f"1 page, counted only: {how} of the {len(groups)} groups"

    scores = {}
    for bench_ids in counted_kpis.values():
        for bench_id in bench_ids:
            scored = [score for score in _comparison_kpi_scores(results, bench_id) if score is not None]
            if scored:
                scores[bench_id] = scored
    candidates = [
        bench_id for bench_ids in counted_kpis.values() for bench_id in bench_ids if bench_id in scores
    ]
    free = room - len(groups)
    if len(candidates) <= free:
        chosen = set(candidates)
        how = f"their {len(candidates)} counted KPIs"
    else:
        picked, rule = _rank(candidates, scores, one_page, free)
        chosen = set(picked)
        how = f"{rule} of their {len(candidates)} counted KPIs"
    kpis = {group: [bench_id for bench_id in counted_kpis[group] if bench_id in chosen] for group in groups}
    return groups, kpis, f"1 page: the {len(groups)} groups counted in the total, {how}"


def _comparison_kpi_name(results: list[dict], bench_id: str) -> str | None:
    """Return the KPI name from the first model that actually produced this benchmark."""
    for result in results:
        benchmark = result["benchmarks"].get(bench_id)
        if benchmark:
            return next((key for key in benchmark.keys() if key != "Score"), None)
    return None


def _scorecard_comparison_cell_colors(scores: list[float]) -> list[str]:
    score_colormap = colormaps["RdYlGn"]
    return [
        (
            SCORECARD_COLORS["invalid_score"]
            if score is None
            else to_hex(score_colormap(min(max(score, 0), 100) / 100), keep_alpha=False).upper()
        )
        for score in scores
    ]


def _scorecard_contrasting_text_color(background: str):
    background_color = colors.HexColor(background)
    luminance = (
        0.2126 * background_color.red + 0.7152 * background_color.green + 0.0722 * background_color.blue
    )
    if luminance < 0.45:
        return colors.white
    return colors.HexColor(SCORECARD_COLORS["body_text"])


def _fit_font_size(
    pdf_canvas,
    text: str,
    font_name: str,
    max_width: float,
    max_size: float = 8,
    min_size: float = 4,
) -> float:
    font_size = max_size
    while font_size > min_size and pdf_canvas.stringWidth(str(text), font_name, font_size) > max_width:
        font_size -= 0.5
    return font_size


def _draw_centered_text(
    pdf_canvas, text: str, x: float, y: float, width: float, font_name: str, font_size: float
):
    text_width = pdf_canvas.stringWidth(str(text), font_name, font_size)
    pdf_canvas.drawString(x + max((width - text_width) / 2, 0), y, str(text))


def save_comparison_as_table(
    filename: Path,
    results: list[dict],
    include_kpis: bool = False,
    full_name: bool = False,
    counted_only: bool = False,
    one_page: str | None = None,
    event_name: str | None = None,
):
    """Draw the score cards of ``results`` side by side, one column each, as a PDF.

    ``event_name`` (the fire or the event the runs were scored on, e.g. ``Hawk Fire``) leads the title.

    ``counted_only`` shows only the groups (and with ``include_kpis`` the KPIs) that count in the
    total. ``one_page`` (a rule of ``ONE_PAGE_RULES``) shows what counts and fits on one page, and
    chooses its own KPIs (see ``_comparison_selection``). The header then says what is shown.
    """
    logger.info("Save multi-model comparison score card report pdf")
    if len(results) < 2:
        raise ValueError("Comparison scorecard requires at least two benchmark results")
    if one_page is not None and include_kpis:
        raise ValueError("A one-page comparison chooses its own KPIs: leave include_kpis out")
    if filename.suffix.lower() != ".pdf":
        filename = filename.with_suffix(".pdf")

    if results[0].get("score_card") is None:
        raise ValueError("Comparison scorecard requires aggregated benchmark results")
    groups, kpis, selection_note = _comparison_selection(
        results, counted_only=counted_only, one_page=one_page, include_kpis=include_kpis
    )
    rows = _scorecard_comparison_rows(
        results, include_kpis=include_kpis, full_name=full_name, groups=groups, kpis=kpis
    )
    base_font = "Helvetica"
    bold_font = "Helvetica-Bold"
    base_font_size = 9
    total_font_size = 10
    page_width, page_height = COMPARISON_PAGE_SIZE
    margin = COMPARISON_MARGIN
    header_height = COMPARISON_HEADER_HEIGHT
    title_height = 9 * mm
    row_height = COMPARISON_ROW_HEIGHT
    footer_height = COMPARISON_FOOTER_HEIGHT
    row_text_offset = 2.2 * mm
    footer_text_offset = 2.2 * mm
    usable_width = page_width - 2 * margin
    label_width = 45 * mm
    for label, _scores in rows:
        label_width = max(label_width, stringWidth(label, bold_font, base_font_size) + 8 * mm)
    label_width = min(label_width, 78 * mm)
    model_col_width = (usable_width - label_width) / len(results)
    min_model_col_width = 24 * mm
    if model_col_width < min_model_col_width:
        model_col_width = min_model_col_width
        page_width = 2 * margin + label_width + model_col_width * len(results)

    pdf_canvas = canvas.Canvas(str(filename.resolve()), pagesize=(page_width, page_height))
    x0 = margin
    table_width = label_width + model_col_width * len(results)
    case_name = _scorecard_benchmark_name(results[0])
    scheme_name = results[0]["score_card"]["aggregation_scheme_name"]
    footer = (
        f"FireBench version: {results[0]['firebench_version']}   "
        f"Reference dataset version: {results[0]['case_version']}"
    )

    def draw_header() -> float:
        y_top_page = page_height - margin
        row_start = y_top_page - header_height

        pdf_canvas.setStrokeColor(colors.HexColor(SCORECARD_COLORS["grid"]))
        pdf_canvas.setLineWidth(0.35)
        pdf_canvas.setFillColor(colors.HexColor(SCORECARD_COLORS["header"]))
        pdf_canvas.rect(x0, row_start, table_width, header_height, stroke=1, fill=1)
        pdf_canvas.setFillColor(colors.white)
        title = f"FireBench comparison {case_name} {scheme_name}"
        if event_name:
            title = f"{event_name}: {title}"
        if selection_note:
            title += f" ({selection_note})"
        pdf_canvas.setFont(
            bold_font,
            _fit_font_size(
                pdf_canvas, title, bold_font, table_width - 6 * mm, max_size=base_font_size, min_size=6
            ),
        )
        pdf_canvas.drawString(x0 + 3 * mm, y_top_page - 8 * mm, title)
        pdf_canvas.line(x0, y_top_page - title_height, x0 + table_width, y_top_page - title_height)
        pdf_canvas.setFont(bold_font, base_font_size)
        pdf_canvas.drawString(x0 + 2 * mm, row_start + 5 * mm, "Score")

        for index, result in enumerate(results):
            cell_x = x0 + label_width + model_col_width * index
            pdf_canvas.line(cell_x, row_start, cell_x, y_top_page - title_height)
            pdf_canvas.setFillColor(colors.white)
            header_text = result["evaluated_model_name"]
            font_size = _fit_font_size(
                pdf_canvas,
                header_text,
                bold_font,
                model_col_width - 4 * mm,
                max_size=base_font_size,
                min_size=5,
            )
            pdf_canvas.setFont(bold_font, font_size)
            _draw_centered_text(
                pdf_canvas,
                header_text,
                cell_x,
                row_start + 5 * mm,
                model_col_width,
                bold_font,
                font_size,
            )
        pdf_canvas.line(x0 + table_width, row_start, x0 + table_width, y_top_page - title_height)
        return row_start

    def draw_footer(footer_y: float):
        pdf_canvas.setFillColor(colors.HexColor(SCORECARD_COLORS["footer"]))
        pdf_canvas.rect(x0, footer_y, table_width, footer_height, stroke=1, fill=1)
        pdf_canvas.setFillColor(colors.white)
        pdf_canvas.setFont(base_font, base_font_size)
        pdf_canvas.drawString(x0 + 2 * mm, footer_y + footer_text_offset, footer)

    def draw_score_row(row_index: int, row_y: float, label: str, scores: list[float]):
        is_total = row_index == 0
        is_group = label.startswith("Group:")
        if is_total:
            label_bg = SCORECARD_COLORS["subheader"]
            label_text_color = colors.white
            label_font = bold_font
            score_font = bold_font
            row_font_size = total_font_size
        elif is_group:
            label_bg = SCORECARD_COLORS["group_row"]
            label_text_color = colors.HexColor(SCORECARD_COLORS["body_text"])
            label_font = bold_font
            score_font = bold_font
            row_font_size = base_font_size
        else:
            label_bg = SCORECARD_COLORS["row_even"] if row_index % 2 == 0 else SCORECARD_COLORS["row_odd"]
            label_text_color = colors.HexColor(SCORECARD_COLORS["body_text"])
            label_font = base_font
            score_font = base_font
            row_font_size = base_font_size

        pdf_canvas.setFillColor(colors.HexColor(label_bg))
        pdf_canvas.rect(x0, row_y, label_width, row_height, stroke=1, fill=1)
        pdf_canvas.setFillColor(label_text_color)
        label_font_size = _fit_font_size(
            pdf_canvas,
            label,
            label_font,
            label_width - 4 * mm,
            max_size=row_font_size,
            min_size=6,
        )
        pdf_canvas.setFont(label_font, label_font_size)
        pdf_canvas.drawString(x0 + 2 * mm, row_y + row_text_offset, label)

        for model_index, (score, background) in enumerate(
            zip(scores, _scorecard_comparison_cell_colors(scores))
        ):
            cell_x = x0 + label_width + model_col_width * model_index
            pdf_canvas.setFillColor(colors.HexColor(background))
            pdf_canvas.rect(cell_x, row_y, model_col_width, row_height, stroke=1, fill=1)
            pdf_canvas.setFillColor(_scorecard_contrasting_text_color(background))
            pdf_canvas.setFont(score_font, row_font_size)
            score_text = NOT_SCORED_TEXT if score is None else f"{score:.2f}"
            text_width = pdf_canvas.stringWidth(score_text, score_font, row_font_size)
            pdf_canvas.drawString(
                cell_x + (model_col_width - text_width) / 2, row_y + row_text_offset, score_text
            )

    pdf_canvas.setTitle("FireBench comparison scorecard")
    row_start_y = draw_header()
    footer_top = margin + footer_height
    page_row_index = 0
    current_table_bottom = row_start_y

    for row_index, (label, scores) in enumerate(rows):
        y = row_start_y - row_height * (page_row_index + 1)
        if y < footer_top:
            draw_footer(current_table_bottom - footer_height)
            pdf_canvas.showPage()
            row_start_y = draw_header()
            page_row_index = 0
            current_table_bottom = row_start_y
            y = row_start_y - row_height
        draw_score_row(row_index, y, label, scores)
        current_table_bottom = y
        page_row_index += 1

    draw_footer(current_table_bottom - footer_height)
    pdf_canvas.showPage()
    pdf_canvas.save()


def save_as_table(
    filename: Path,
    data: dict,
    signed: bool,
    certificate_name: str,
    full_name: bool = False,
):
    logger.info("Save data dict as score card report pdf")
    if filename.suffix.lower() != ".pdf":
        filename = filename.with_suffix(".pdf")

    COLOR_ROWS = [
        SCORECARD_COLORS["row_even"],
        SCORECARD_COLORS["row_odd"],
    ]

    verif_lvl = data.get("verification_lvl", DEFAULT_VL)

    if signed:
        # Check validity of signature
        verif = verify_certificate_in_dict(data, certificate_name)
        if not verif["valid"]:
            raise ValueError("Certificate verification failed")

    # ------------------------------------------------------------------
    # 1) Create PDF
    # ------------------------------------------------------------------
    doc = SimpleDocTemplate(
        str(filename.resolve()),
        pagesize=A4,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )

    text_table = []

    # header
    scheme_name = "0"
    valid_scheme = False
    if "score_card" in data:
        scheme_name = data["score_card"]["aggregation_scheme_name"]
        valid_scheme = True
        total_score = data["score_card"].get("Score Total")
        text_table.append(
            _scorecard_title(
                data,
                scheme_name,
                verif_lvl,
                NOT_SCORED_TEXT if total_score is None else f"{total_score:.2f}",
            )
        )
    else:
        # Aggregation scheme is 0 or invalid
        scheme_name = "No agg"
        text_table.append(_scorecard_title(data, scheme_name, verif_lvl, "Invalid"))
    text_table.append(["Benchmark ID/Group Name", "KPI value", "Weight", "Score"])

    # rows
    group_rows = []
    if valid_scheme:
        for group_name, group_content in data["score_card"]["Scheme"].items():
            # add group row. A group with no eligible weighted KPI is dropped by aggregation, so it
            # is reported without a score instead of being hidden from the report.
            group_score = data["score_card"].get(f"Score {group_name}")
            group_rows.append(len(text_table))
            text_table.append(
                [
                    f"Group: {_scorecard_group_name(data, group_name)}",
                    "",
                    f"{group_content['weight']}",
                    NOT_SCORED_TEXT if group_score is None else f"{group_score:.2f}",
                ]
            )
            # add benchamrk rows
            for bench_id, bench_weight in group_content["benchmarks"].items():
                if bench_id not in data["benchmarks"]:
                    # The KPI was ignored, so it produced neither a KPI value nor a score.
                    continue
                for key, item in data["benchmarks"][bench_id].items():
                    if key == "Score":
                        bench_score = item
                        kpi_name = [i for i in data["benchmarks"][bench_id].keys() if i != "Score"][0]
                    else:
                        # KPI
                        kpi_score = item
                text_table.append(
                    [
                        _scorecard_kpi_name(bench_id, kpi_name, full_name=full_name),
                        f"{kpi_score:.2e}",
                        f"{bench_weight}",
                        f"{bench_score:.2f}",
                    ]
                )
    else:
        # Only print benchmarks
        for bench_id in data["benchmarks"].keys():
            for key, item in data["benchmarks"][bench_id].items():
                if key == "Score":
                    bench_score = item
                else:
                    kpi_score = item
            text_table.append(
                [
                    _scorecard_kpi_name(bench_id, bench_id, full_name=full_name),
                    f"{kpi_score:.2e}",
                    "None",
                    f"{bench_score:.2f}",
                ]
            )

    # footer
    text_table.append([_scorecard_footer(data), "", "", ""])

    nb_rows = len(text_table)

    col_widths = [130 * mm, 20 * mm, 20 * mm, 20 * mm]

    # ------------------------------------------------------------------
    # 3) Table style with both merges
    # ------------------------------------------------------------------
    table_style = [
        # === MERGE FIRST 2 COLUMNS OF FIRST ROW ===
        ("SPAN", (0, 0), (1, 0)),
        # === MERGE ALL 4 COLUMNS OF LAST ROW ===
        ("SPAN", (0, nb_rows - 1), (3, nb_rows - 1)),
        # Borders
        ("BOX", (0, 0), (-1, -1), 0.75, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(SCORECARD_COLORS["grid"])),
        # Background colors for clarity
        (
            "BACKGROUND",
            (0, 0),
            (-1, -1),
            colors.HexColor(SCORECARD_COLORS["header"]),
        ),  # merged header row
        (
            "BACKGROUND",
            (0, 1),
            (-1, 1),
            colors.HexColor(SCORECARD_COLORS["subheader"]),
        ),  # merged header row
        (
            "BACKGROUND",
            (0, -1),
            (-1, -1),
            colors.HexColor(SCORECARD_COLORS["footer"]),
        ),  # merged footer row
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        # Alignment
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (0, -1), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Fonts
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONT", (2, 0), (3, 0), "Helvetica-Bold", 9),
    ]

    for i in range(nb_rows - 3):
        table_style.append(
            (
                "BACKGROUND",
                (0, i + 2),
                (-1, i + 2),
                colors.HexColor(COLOR_ROWS[i % len(COLOR_ROWS)]),
            ),  # merged header row
        )
        table_style.append(
            ("TEXTCOLOR", (0, i + 2), (-1, i + 2), colors.HexColor(SCORECARD_COLORS["body_text"]))
        )
        table_style.append(("ALIGN", (0, i + 1), (0, i + 1), "LEFT"))

    if valid_scheme:
        total_score = data["score_card"].get("Score Total")
        table_style.append(
            (
                "BACKGROUND",
                (3, 0),
                (3, 0),
                colors.HexColor(
                    SCORECARD_COLORS["invalid_score"]
                    if total_score is None
                    else _score_to_color(total_score)
                ),
            ),  # merged header row
        )
        table_style.append(("TEXTCOLOR", (3, 0), (3, 0), colors.white))
        for i_row in group_rows:
            table_style.append(
                (
                    "BACKGROUND",
                    (0, i_row),
                    (-1, i_row),
                    colors.HexColor(SCORECARD_COLORS["group_row"]),
                ),
            )
            table_style.append(
                ("TEXTCOLOR", (0, i_row), (-1, i_row), colors.HexColor(SCORECARD_COLORS["body_text"]))
            )
    else:
        text_table[0][3] = "INVALID"
        table_style.append(
            (
                "BACKGROUND",
                (3, 0),
                (3, 0),
                colors.HexColor(SCORECARD_COLORS["invalid_score"]),
            ),  # merged header row
        )
        table_style.append(("TEXTCOLOR", (3, 0), (3, 0), colors.white))
    # VL colors
    table_style.append(
        (
            "BACKGROUND",
            (2, 0),
            (2, 0),
            colors.HexColor(VERIFICATION_LEVEL_COLORS.get(verif_lvl, "#B03A2E")),
        ),  # merged header row
    )

    table = Table(text_table, colWidths=col_widths, repeatRows=2)
    style = TableStyle(table_style)
    table.setStyle(style)

    doc.build([table])
