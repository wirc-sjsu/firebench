from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
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
