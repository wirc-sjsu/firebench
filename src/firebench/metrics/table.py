from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from pathlib import Path
import re
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
    "comparison_best": "#228833",
    "comparison_worst": "#B03A2E",
    "comparison_neutral": "#FFFFFF",
}


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


def _scorecard_group_name(data: dict, group_name: str) -> str:
    return data.get("score_card", {}).get("group_display_names", {}).get(group_name, group_name)


def _scorecard_kpi_name(bench_id: str, kpi_name: str, full_name: bool = False) -> str:
    if full_name:
        return f"{bench_id}: {kpi_name}"
    return re.sub(r"\s+(?:WH\d+|W\d+)$", "", kpi_name)


def _scorecard_comparison_rows(results: list[dict]) -> list[tuple[str, list[float]]]:
    first_result = results[0]
    score_card = first_result.get("score_card")
    if score_card is None:
        raise ValueError("Comparison scorecard requires aggregated benchmark results")

    rows = [("Total Score", [result["score_card"]["Score Total"] for result in results])]
    for group_name in score_card["Scheme"].keys():
        rows.append(
            (
                f"Group: {_scorecard_group_name(first_result, group_name)}",
                [result["score_card"][f"Score {group_name}"] for result in results],
            )
        )
    return rows


def _scorecard_comparison_cell_colors(scores: list[float]) -> list[str]:
    if not scores:
        return []

    unique_scores = set(scores)
    if len(unique_scores) <= 1:
        return [SCORECARD_COLORS["comparison_neutral"] for _ in scores]

    best_score = max(scores)
    worst_score = min(scores)
    score_colors = []
    for score in scores:
        if score == best_score:
            score_colors.append(SCORECARD_COLORS["comparison_best"])
        elif score == worst_score:
            score_colors.append(SCORECARD_COLORS["comparison_worst"])
        else:
            score_colors.append(SCORECARD_COLORS["comparison_neutral"])
    return score_colors


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


def save_comparison_as_table(filename: Path, results: list[dict]):
    logger.info("Save multi-model comparison score card report pdf")
    if len(results) < 2:
        raise ValueError("Comparison scorecard requires at least two benchmark results")
    if filename.suffix.lower() != ".pdf":
        filename = filename.with_suffix(".pdf")

    rows = _scorecard_comparison_rows(results)
    page_width, page_height = landscape(A4)
    margin = 12 * mm
    header_height = 22 * mm
    title_height = 9 * mm
    row_height = 10 * mm
    footer_height = 9 * mm
    usable_width = page_width - 2 * margin
    label_width = 45 * mm
    for label, _scores in rows:
        label_width = max(label_width, stringWidth(label, "Helvetica-Bold", 8) + 8 * mm)
    label_width = min(label_width, 78 * mm)
    model_col_width = (usable_width - label_width) / len(results)
    min_model_col_width = 24 * mm
    if model_col_width < min_model_col_width:
        model_col_width = min_model_col_width
        page_width = 2 * margin + label_width + model_col_width * len(results)

    pdf_canvas = canvas.Canvas(str(filename.resolve()), pagesize=(page_width, page_height))
    x0 = margin
    y_top = page_height - margin
    table_width = label_width + model_col_width * len(results)
    row_start_y = y_top - header_height
    footer_y = row_start_y - row_height * len(rows) - footer_height

    pdf_canvas.setTitle("FireBench comparison scorecard")
    pdf_canvas.setStrokeColor(colors.HexColor(SCORECARD_COLORS["grid"]))
    pdf_canvas.setLineWidth(0.35)

    pdf_canvas.setFillColor(colors.HexColor(SCORECARD_COLORS["header"]))
    pdf_canvas.rect(x0, row_start_y, table_width, header_height, stroke=1, fill=1)
    pdf_canvas.setFillColor(colors.white)
    pdf_canvas.setFont("Helvetica-Bold", 10)
    case_name = _scorecard_benchmark_name(results[0])
    scheme_name = results[0]["score_card"]["aggregation_scheme_name"]
    pdf_canvas.drawString(x0 + 3 * mm, y_top - 8 * mm, f"FireBench comparison {case_name} {scheme_name}")
    pdf_canvas.line(x0, y_top - title_height, x0 + table_width, y_top - title_height)
    pdf_canvas.setFont("Helvetica-Bold", 8)
    pdf_canvas.drawString(x0 + 2 * mm, row_start_y + 5 * mm, "Score")

    for index, result in enumerate(results):
        cell_x = x0 + label_width + model_col_width * index
        pdf_canvas.line(cell_x, row_start_y, cell_x, y_top - title_height)
        pdf_canvas.setFillColor(colors.white)
        header_text = result["evaluated_model_name"]
        font_size = _fit_font_size(
            pdf_canvas,
            header_text,
            "Helvetica-Bold",
            model_col_width - 4 * mm,
            max_size=8,
            min_size=4,
        )
        pdf_canvas.setFont("Helvetica-Bold", font_size)
        _draw_centered_text(
            pdf_canvas,
            header_text,
            cell_x,
            row_start_y + 5 * mm,
            model_col_width,
            "Helvetica-Bold",
            font_size,
        )
    pdf_canvas.line(x0 + table_width, row_start_y, x0 + table_width, y_top - title_height)

    for row_index, (label, scores) in enumerate(rows):
        y = row_start_y - row_height * (row_index + 1)
        label_bg = SCORECARD_COLORS["row_even"] if row_index % 2 == 0 else SCORECARD_COLORS["row_odd"]
        pdf_canvas.setFillColor(colors.HexColor(label_bg))
        pdf_canvas.rect(x0, y, label_width, row_height, stroke=1, fill=1)
        pdf_canvas.setFillColor(colors.HexColor(SCORECARD_COLORS["body_text"]))
        pdf_canvas.setFont("Helvetica-Bold" if row_index == 0 else "Helvetica", 8)
        pdf_canvas.drawString(x0 + 2 * mm, y + 3.2 * mm, label)

        for model_index, (score, background) in enumerate(
            zip(scores, _scorecard_comparison_cell_colors(scores))
        ):
            cell_x = x0 + label_width + model_col_width * model_index
            pdf_canvas.setFillColor(colors.HexColor(background))
            pdf_canvas.rect(cell_x, y, model_col_width, row_height, stroke=1, fill=1)
            pdf_canvas.setFillColor(
                colors.white
                if background in {SCORECARD_COLORS["comparison_best"], SCORECARD_COLORS["comparison_worst"]}
                else colors.HexColor(SCORECARD_COLORS["body_text"])
            )
            pdf_canvas.setFont("Helvetica-Bold", 8)
            score_text = f"{score:.2f}"
            text_width = pdf_canvas.stringWidth(score_text, "Helvetica-Bold", 8)
            pdf_canvas.drawString(cell_x + (model_col_width - text_width) / 2, y + 3.2 * mm, score_text)

    pdf_canvas.setFillColor(colors.HexColor(SCORECARD_COLORS["footer"]))
    pdf_canvas.rect(x0, footer_y, table_width, footer_height, stroke=1, fill=1)
    pdf_canvas.setFillColor(colors.white)
    pdf_canvas.setFont("Helvetica", 8)
    footer = (
        f"FireBench version: {results[0]['firebench_version']}   "
        f"Reference dataset version: {results[0]['case_version']}"
    )
    pdf_canvas.drawString(x0 + 2 * mm, footer_y + 3 * mm, footer)

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

    # Default Verification lvl
    verif_lvl = DEFAULT_VL

    if signed:
        # Check validity of signature
        verif = verify_certificate_in_dict(data, certificate_name)
        if not verif["valid"]:
            raise ValueError("Certificate verification failed")
        verif_lvl = data.get("verification_lvl", DEFAULT_VL)

    # Get the number of row
    nb_rows = 3  # header and footer
    nb_bench = len(data["benchmarks"].keys())
    score_card = data.get("score_card")
    if score_card is None:
        # No aggregation, no total score
        nb_rows += nb_bench
    else:
        # get number of rows from schemes
        for group_name, group_content in data["score_card"]["Scheme"].items():
            nb_rows += len(group_content["benchmarks"]) + 1

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
        text_table.append(
            _scorecard_title(data, scheme_name, verif_lvl, f"{data['score_card']['Score Total']:.2f}")
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
            # add group row
            group_score = data["score_card"][f"Score {group_name}"]
            group_rows.append(len(text_table))
            text_table.append(
                [
                    f"Group: {_scorecard_group_name(data, group_name)}",
                    "",
                    f"{group_content['weight']}",
                    f"{group_score:.2f}",
                ]
            )
            # add benchamrk rows
            for bench_id, bench_weight in group_content["benchmarks"].items():
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
    text_table.append(
        [
            f"FireBench version: {data['firebench_version']}   "
            f"Reference dataset version: {data['case_version']}",
            "",
            "",
            "",
        ]
    )

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
        table_style.append(
            (
                "BACKGROUND",
                (3, 0),
                (3, 0),
                colors.HexColor(_score_to_color(data["score_card"]["Score Total"])),
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
