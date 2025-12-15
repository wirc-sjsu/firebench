from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from pathlib import Path
from ..tools import logger


def _score_to_color(score):
    """
    Map a score from 0 to 100 to a color from red -> yellow -> green.
    Output: hex string "#RRGGBB".
    """
    if score < 33.33:
        return "#D6452A"

    if score < 66.66:
        return "#E8C441"

    return "#6BAF5F"


def save_as_table(filename: Path, data: dict):
    logger.info("Save data dict as score card report pdf")
    if filename.suffix.lower() != ".pdf":
        filename = filename.with_suffix(".pdf")

    COLOR_ROWS = [
        "#f7d5cd",
        "#fbebe8",
    ]

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
        pagesize=(165 * mm, nb_rows * 8 * mm),
        leftMargin=0 * mm,
        rightMargin=0 * mm,
        topMargin=0 * mm,
        bottomMargin=0 * mm,
    )

    text_table = []

    # header
    scheme_name = "0"
    valid_scheme = False
    if "score_card" in data:
        scheme_name = data["score_card"]["aggregation_scheme_name"]
        valid_scheme = True
        text_table.append(
            [
                f"Total Score {data['case_id']} agg. {scheme_name}: {data['evaluated_model_name']}",
                "",
                "",
                f"{data['score_card']['Score Total']:.2f}",
            ]
        )
    else:
        # Aggregation scheme is 0 or invalid
        scheme_name = "No agg"
        text_table.append(
            [
                f"Total Score {data['case_id']} agg. {scheme_name}: {data['evaluated_model_name']}",
                "",
                "",
                f"Invalid",
            ]
        )
    text_table.append(["Benchmark ID/Group Name", "KPI value", "Weight", "Score"])

    # rows
    group_rows = []
    if valid_scheme:
        for group_name, group_content in data["score_card"]["Scheme"].items():
            # add group row
            group_score = data["score_card"][f"Score {group_name}"]
            group_rows.append(len(text_table))
            text_table.append(
                [f"Group: {group_name}", "", f"{group_content['weight']}", f"{group_score:.2f}"]
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
                    [f"{kpi_name}", f"{kpi_score:.2e}", f"{bench_weight}", f"{bench_score:.2f}"]
                )
    else:
        # Only print benchmarks
        for bench_id in data["benchmarks"].keys():
            for key, item in data["benchmarks"][bench_id].items():
                if key == "Score":
                    bench_score = item
                else:
                    kpi_score = item
            text_table.append([f"{bench_id}", f"{kpi_score:.2e}", "None", f"{bench_score:.2f}"])

    # footer
    text_table.append(
        [
            f"FireBench version: {data['firebench_version']}   case version: {data['case_version']}",
            "",
            "",
            "",
        ]
    )

    col_widths = [100 * mm, 20 * mm, 20 * mm, 20 * mm]

    # ------------------------------------------------------------------
    # 3) Table style with both merges
    # ------------------------------------------------------------------
    table_style = [
        # === MERGE FIRST 3 COLUMNS OF FIRST ROW ===
        ("SPAN", (0, 0), (2, 0)),
        # === MERGE ALL 4 COLUMNS OF LAST ROW ===
        ("SPAN", (0, nb_rows - 1), (3, nb_rows - 1)),
        # Borders
        ("BOX", (0, 0), (-1, -1), 0.75, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        # Background colors for clarity
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#c04f15")),  # merged header row
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#e97132")),  # merged header row
        (
            "BACKGROUND",
            (0, -1),
            (-1, -1),
            colors.HexColor("#A79F9A"),
        ),  # merged footer row
        # Alignment
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (0, -1), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Fonts
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONT", (3, 0), (3, 0), "Helvetica-Bold", 9),
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
        for i_row in group_rows:
            table_style.append(
                ("BACKGROUND", (0, i_row), (-1, i_row), colors.HexColor("#f2aa84")),
            )
    else:
        text_table[0][2] = "INVALID"
        table_style.append(
            ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#ff0000")),  # merged header row
        )

    table = Table(text_table, colWidths=col_widths)
    style = TableStyle(table_style)
    table.setStyle(style)

    doc.build([table])
