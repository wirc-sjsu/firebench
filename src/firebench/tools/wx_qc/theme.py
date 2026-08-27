"""Semantic design tokens and tkinter style setup for the weather QC UI.

Provides centralized color, font, and spacing constants used throughout the GUI,
plus functions to initialize and customize ttk styles. All color values are
semantic (e.g., ERROR_BG, WARN_FG) rather than hard-coded hex in UI code.
Module imports only ttk/stdlib to avoid circular dependencies.
"""

from tkinter import ttk

ACCENT = "#2f6fa8"

ERROR_BG = "#ffd6d6"
WARN_BG = "#fff5cc"
OK_BG = "#d9f2d9"

ERROR_FG = "#cc0000"
WARN_FG = "#886600"

OUTAGE_SHADE = ERROR_BG

MUTED = "#999999"

SKIP_RED = "#d62728"
GREEN_OK = "#2ca02c"
UNDECIDED = MUTED
MISSING_MARKER = "#888"

PLOT_BG = "white"

FONT_SMALL = ("", 8)
FONT_SECTION = ("", 9, "bold")
FONT_MONO = ("Courier", 9)
FONT_STATUS = ("TkDefaultFont", 11, "bold")

PAD = 4
PAD_LG = 8

FIG_DPI = 96


def _darken_hex(hexcolor, factor):
    """Scale RGB toward black by factor (0-1), preserving hue/saturation.

    Args:
        hexcolor (str): Hex color code, with or without leading "#" (e.g., "#abc123" or "abc123").
        factor (float): Scaling factor in range [0, 1]. factor=1.0 returns original color,
            factor=0.0 returns black.

    Returns:
        str: Darkened hex color code with "#" prefix.
    """
    hexcolor = hexcolor.lstrip("#")
    r, g, b = (int(hexcolor[i : i + 2], 16) for i in (0, 2, 4))
    return f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"


def setup_style(root):
    """Bootstrap ttk style and return derived colors (e.g., header background).

    Configures ttk themes, custom styles, and layouts for Treeview, TEntry, Notebook,
    and custom tab/label styles. Derives dynamic colors (e.g., header_bg) from the
    active theme to maintain visual consistency across platforms.

    Args:
        root: Tkinter root window (required for ttk.Style).

    Returns:
        dict: A dictionary with derived color keys (e.g., "header_bg" -> hex color string).
    """
    style = ttk.Style(root)
    # Use clam theme: aqua (macOS default) silently ignores Treeview
    # row/tag background colors, making per-row selection invisible.
    style.theme_use("clam")
    # Clam's TEntry caret renders invisible on this Tcl/Tk build.
    # Force visible via explicit insertwidth.
    style.configure("TEntry", insertwidth=2, insertbackground="black")
    style.configure(
        "Treeview", foreground="black", background="white", fieldbackground="white", rowheight=20
    )
    style.configure("Treeview.Heading", foreground="black")
    style.configure(
        "Pane.Treeview", background="#eceff1", fieldbackground="#eceff1", borderwidth=0, rowheight=22
    )
    # Empty map preserves state-independent colors (no state-specific overrides).
    style.map("Pane.Treeview", background=[], foreground=[])
    style.configure("Mono.Treeview", font=FONT_MONO)
    # Variable tab-strip: use Notebook.tab element directly for native tab visuals.
    # Reusing Toolbutton with only recoloring keeps clam's per-state relief
    # settings (flat/sunken/raised) which makes it read as a button, not a tab.
    _tab_bg = style.lookup("TNotebook.Tab", "background") or "#bab5ab"
    _tab_bg_sel = style.lookup("TNotebook.Tab", "background", ("selected",)) or "#dcdad5"
    _tab_fg = style.lookup("TNotebook.Tab", "foreground") or "black"
    _tab_pad = style.lookup("TNotebook.Tab", "padding") or (6, 2, 6, 2)
    _tab_font = style.lookup("TNotebook.Tab", "font") or "TkDefaultFont"
    style.layout(
        "VarTab.Toolbutton",
        [
            (
                "Notebook.tab",
                {
                    "sticky": "nswe",
                    "children": [
                        (
                            "Toolbutton.padding",
                            {"sticky": "nswe", "children": [("Toolbutton.label", {"sticky": "nswe"})]},
                        )
                    ],
                },
            )
        ],
    )
    style.configure(
        "VarTab.Toolbutton", padding=_tab_pad, font=_tab_font, background=_tab_bg, foreground=_tab_fg
    )
    style.map(
        "VarTab.Toolbutton",
        background=[("selected", _tab_bg_sel), ("active", _tab_bg_sel)],
        foreground=[("disabled", MUTED)],
        relief=[],
    )
    # Pane-header needs dark bg for contrast with white text. Clam has no native
    # dark tone; derive one from its TNotebook bordercolor to stay within theme.
    header_bg = _darken_hex(style.lookup("TNotebook", "bordercolor") or "#9e9a91", 0.42)
    # Muted label foreground: derive from clam's disabled-label color.
    style.configure("Muted.TLabel", foreground=style.lookup("TLabel", "foreground", ("disabled",)) or MUTED)
    style.configure("Section.TLabel", font=FONT_SECTION)
    style.configure("Status.TLabel", font=FONT_STATUS)
    style.configure("Small.TButton", font=FONT_SMALL)
    return {"header_bg": header_bg}
