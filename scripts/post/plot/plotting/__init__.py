# plotting — Matplotlib figure template (styles + helpers)
#
# Usage:
#   from plotting import use_style, save_figure, plot_line
#
from .mpl_template import (
    BODY_FONT,
    TITLE_FONT,
    add_reference_lines,
    add_textbox,
    annotate_point,
    apply_marker_style,
    apply_oldschool_axes,
    dual_axis,
    make_legend,
    new_figure,
    plot_bar,
    plot_line,
    plot_with_band,
    print_file_report,
    register_fonts,
    save_figure,
    set_axis_sci,
    set_subtitle,
    set_suptitle,
    set_title,
    style_context,
    use_style,
)

__all__ = [
    "BODY_FONT",
    "TITLE_FONT",
    "add_reference_lines",
    "add_textbox",
    "annotate_point",
    "apply_marker_style",
    "apply_oldschool_axes",
    "dual_axis",
    "make_legend",
    "new_figure",
    "plot_bar",
    "plot_line",
    "plot_with_band",
    "print_file_report",
    "register_fonts",
    "save_figure",
    "set_axis_sci",
    "set_subtitle",
    "set_suptitle",
    "set_title",
    "style_context",
    "use_style",
]
