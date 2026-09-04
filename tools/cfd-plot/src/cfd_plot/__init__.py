# cfd_plot — Matplotlib figure template (styles + helpers)
#
# Usage:
#   from cfd_plot import use_style, save_figure, plot_line
#
from .mpl_template import (
    BODY_FONT,
    TITLE_FONT,
    add_reference_lines,
    add_shared_colorbar,
    add_textbox,
    annotate_point,
    apply_marker_style,
    apply_oldschool_axes,
    dual_axis,
    fill_between_curves,
    make_figure_legend,
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
    sync_axes_limits,
    use_style,
)

# --- 2D scalar field plotting ------------------------------------------------
from .field2d import (
    interpolate_field2d,
    plot_contour,
    plot_contourf,
    plot_imshow,
    plot_pcolormesh,
    plot_pcolormesh_interp,
)

# --- 2D vector field plotting ------------------------------------------------
from .vector2d import (
    compute_speed,
    plot_quiver,
    plot_streamplot,
    subsample_vectors,
)

# --- Combined 2D plots -------------------------------------------------------
from .composite2d import (
    plot_contour_quiver,
)

# --- Batch curve plotting ----------------------------------------------------
from .batch import (
    BatchPlotContext,
    DEFAULT_FLIGHT_POINT_KEYS,
    FOLD_Y_STEM,
    FoldSpec,
    batch_compare_flight_points,
    batch_plot,
    build_compare_output_path,
    build_output_path,
    config_extra_keys,
    config_style_keys,
    discover_flight_point_values,
    format_axis_label,
    format_axis_title_label,
    format_flight_point_title_suffix,
    format_plot_title,
    ignored_config_keys,
    iter_fixed_sweep_combinations,
    iter_flight_points,
    varying_flight_keys,
)

# --- Domain regions ----------------------------------------------------------
from .domains import (
    Domain,
    DomainSpan,
    domain_segments,
    plot_domains,
)

# --- Animation (GIF / MP4) ---------------------------------------------------
from .anim import (
    PRESETS,
    AnimationResult,
    AnimPreset,
    Animator,
    animate,
    animate_frames,
    animate_sweep,
    ffmpeg_available,
    frames_to_gif,
    frames_to_mp4,
)

# --- Paper-figure assembly ---------------------------------------------------
from .layout import (
    panel_labels,
)

from .palettes import (
    PALETTES,
    palette_colors,
    palette_context,
    set_palette,
)

# --- PDF reports -------------------------------------------------------------
from .pdf import (
    PAGE_SIZES,
    PdfReportSpec,
    ReportSection,
    contact_sheet,
    pdf_report,
)

# --- Cleaning a generated figure tree ----------------------------------------
from .cleanup import (
    FIGURE_SUFFIXES,
    CleanReport,
    clean_figure_dir,
)

from .prep import (
    dataframe_to_grid,
    dataframe_to_masked_grid,
    extract_slice2d,
    mask_field,
    reshape_structured2d,
)

__all__ = [
    # Style / figure lifecycle
    "BODY_FONT",
    "TITLE_FONT",
    "new_figure",
    "register_fonts",
    "style_context",
    "use_style",
    # 1D plot helpers
    "apply_marker_style",
    "fill_between_curves",
    "plot_bar",
    "plot_line",
    "plot_with_band",
    # 2D scalar field
    "interpolate_field2d",
    "plot_contour",
    "plot_contourf",
    "plot_imshow",
    "plot_pcolormesh",
    "plot_pcolormesh_interp",
    # 2D vector field
    "compute_speed",
    "plot_quiver",
    "plot_streamplot",
    "subsample_vectors",
    # 2D composite
    "plot_contour_quiver",
    # Batch curve plotting
    "BatchPlotContext",
    "DEFAULT_FLIGHT_POINT_KEYS",
    "FOLD_Y_STEM",
    "FoldSpec",
    "batch_compare_flight_points",
    "batch_plot",
    "build_compare_output_path",
    "build_output_path",
    "config_extra_keys",
    "config_style_keys",
    "discover_flight_point_values",
    "format_axis_label",
    "format_axis_title_label",
    "format_flight_point_title_suffix",
    "format_plot_title",
    "ignored_config_keys",
    "iter_fixed_sweep_combinations",
    "iter_flight_points",
    "varying_flight_keys",
    # Domain regions
    "Domain",
    "DomainSpan",
    "domain_segments",
    "plot_domains",
    # Animation (GIF / MP4)
    "AnimPreset",
    "AnimationResult",
    "Animator",
    "PRESETS",
    "animate",
    "animate_frames",
    "animate_sweep",
    "ffmpeg_available",
    "frames_to_gif",
    "frames_to_mp4",
    # Paper-figure assembly
    "PALETTES",
    "palette_colors",
    "palette_context",
    "panel_labels",
    "set_palette",
    # PDF reports
    "PAGE_SIZES",
    "PdfReportSpec",
    "ReportSection",
    "contact_sheet",
    "pdf_report",
    # Cleaning a generated figure tree
    "CleanReport",
    "FIGURE_SUFFIXES",
    "clean_figure_dir",
    # Data preparation
    "dataframe_to_grid",
    "dataframe_to_masked_grid",
    "extract_slice2d",
    "mask_field",
    "reshape_structured2d",
    # Axes / annotation helpers
    "add_reference_lines",
    "add_shared_colorbar",
    "add_textbox",
    "annotate_point",
    "apply_oldschool_axes",
    "dual_axis",
    "make_figure_legend",
    "make_legend",
    "set_axis_sci",
    "set_subtitle",
    "set_suptitle",
    "set_title",
    "sync_axes_limits",
    # Export
    "print_file_report",
    "save_figure",
]
