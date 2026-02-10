# plotting — Matplotlib figure template (styles + helpers)
#
# Usage:
#   from plotting import use_style, save_figure, plot_line
#
from .mpl_template import (
    use_style,
    style_context,
    new_figure,
    save_figure,
    plot_line,
    apply_marker_style,
)

__all__ = [
    "use_style",
    "style_context",
    "new_figure",
    "save_figure",
    "plot_line",
    "apply_marker_style",
]
