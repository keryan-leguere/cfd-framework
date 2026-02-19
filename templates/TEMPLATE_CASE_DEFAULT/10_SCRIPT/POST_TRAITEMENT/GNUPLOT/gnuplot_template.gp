###############################################################################
# TEMPLATE FOR GNUPLOT
# Author: KL
# Date: November 2025
###############################################################################

# --- OUTPUT SETTINGS ---------------------------------------------------------
# "pngcairo" → high-quality PNG (antialiased)
# For vector graphics use instead:
#   set terminal pdfcairo enhanced font "Latin Modern Roman,26"
# or LaTeX integration:
#   set terminal epslatex size 6,4 color colortext font "lmroman10,10"
set terminal pngcairo size 1600,1200 enhanced font "Latin Modern Roman,26"
set output OUTPUT_FILE

# --- BORDER, TICKS & GRID ----------------------------------------------------
# Border value = 1+2+4+8 = 15 → all 4 sides
set border 15 lw 3 lc rgb "black"
set xtics nomirror font "Latin Modern Roman,26"
set ytics nomirror font "Latin Modern Roman,26"
set format x "%.2f"
set format y "%.3f"

# Grid options (uncomment for customization)
#set grid lw 3 lc rgb "#bbbbbb" dashtype 2   # dashed gray grid
#set grid xtics ytics back                   # grid only on back layer
#set grid mxtics mytics                      # minor grid lines

# --- MARGINS -----------------------------------------------------------------
# Adjust to control whitespace around the plot
set tmargin 3
set bmargin 3.5
set lmargin 14
set rmargin 4

# --- DEFAULT LABELS ---
if (!exists("XLABEL")) XLABEL="XLABEL" 
set xlabel XLABEL font "Latin Modern Roman,36"

if (!exists("YLABEL")) YLABEL="YLABEL"
set ylabel YLABEL font "Latin Modern Roman,36" offset -2,0

if (!exists("TITLE")) TITLE="TITLE"
set title TITLE font "Latin Modern Roman,34"

# === OPTIONAL: Subtitle Examples ===
# SUBTITLE = "Re = 10^{5} (L=1), M = 0.2"
if (exists("SUBTITLE")) set label 1 SUBTITLE at graph 0.5, 1.04 center font "Latin Modern Roman,28"


# --- LEGEND (KEY) ------------------------------------------------------------
set key top right box lw 3
set key font "Latin Modern Roman,26"
set key spacing 1.0
set key width -1.0
if (exists("GPVAL_VERSION") && GPVAL_VERSION >= 5) set key samplen 1.5

# --- LINE STYLES -------------------------------------------------------------
# You can define reusable line styles with colors, markers, and dashes.
# "pt" = point type (symbol), "ps" = point size, "dt" = dash type
# Useful palette: https://godsnotwheregodsnot.blogspot.com/2012/09/color-palette-table-for-gnuplot.html

# === Example Line Styles ===
# REF# To plot with markers visible, use "with linespoints" instead of "with lines"

# For white fill markers (used in style 1)
set style fill solid border rgb "black"

# --- 1. Black line, circle marker, white fill --------------------------------
# Classic publication-style: black solid line, hollow circle marker
set style line 1 lc rgb "#000000" lw 5 lt 1 pt 7 ps 1.6 dt solid    # black, circle marker (hollow)

# --- 2. Red dashed line, square marker ---------------------------------------
# Red tone, square marker, short dashes (dt 2)
set style line 2 lc rgb "#d62728" lw 5 lt 1 pt 9 ps 1.4 dt solid         # red, square marker

# --- 3. Green solid line, triangle marker ------------------------------------
# Natural green with upward triangle markers
set style line 3 lc rgb "#2ca02c" lw 5 lt 1 pt 5 ps 1.6 dt solid     # green, triangle

# --- 4. Purple dotted line, cross marker -------------------------------------
# Muted purple with small cross symbols, dotted line
set style line 4 lc rgb "#9467bd" lw 5 lt 3 pt 11 ps 1.4 dt solid        # purple, cross marker

# --- 5. Orange dash-dot line, diamond marker ---------------------------------
# Warm orange tone, diamond markers
set style line 5 lc rgb "#ff7f0e" lw 5 lt 1 pt 13 ps 1.5 dt 5        # orange, diamond marker

# --- 6. Cyan long-dashed line, triangle-down marker ---------------------------
# Cool cyan tone, inverted triangle marker
set style line 6 lc rgb "#17becf" lw 5 lt 1 pt 3 ps 1.6 dt 6         # cyan, triangle-down marker

# --- 7. Dark gray solid line, filled square marker ----------------------------
# Subtle neutral color, good for reference curves
set style line 7 lc rgb "#555555" lw 5 lt 1 pt 4 ps 1.5 dt solid     # gray, filled square marker

# --- 8. Magenta dashed line, star marker -------------------------------------
# Strong contrast color for emphasis
set style line 8 lc rgb "#e377c2" lw 5 lt 2 pt 12 ps 1.6 dt 7        # magenta, star marker

# --- 9. Navy blue dash-dot-dot line, circle marker ----------------------------
# Deep blue for clarity, mixed dash-dot style
set style line 9 lc rgb "#1f3a93" lw 5 lt 1 pt 7 ps 1.5 dt 8         # navy, circle marker

# --- 10. Olive green dotted line, plus marker --------------------------------
# Earth tone, minimalist marker — great for subdued secondary data
set style line 10 lc rgb "#8c7b00" lw 5 lt 3 pt 2 ps 1.4 dt 3        # olive, plus marker

# Example:
# plot FILE using 1:2 with linespoints ls 1 title "Dataset A"

