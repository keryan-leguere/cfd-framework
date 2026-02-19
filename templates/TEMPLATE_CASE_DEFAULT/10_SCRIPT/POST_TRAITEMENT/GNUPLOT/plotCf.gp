###############################################################################
# Example plot using Arthur’s global template
###############################################################################

# --- SPECIFIC VARIABLES ---
OUTPUT_FILE = "./09_POST_TRAITEMENT/FIGURE/2DZP_Cf.png"
XLABEL = "{/LMRoman10-Italic x}"
YLABEL = "C_{f}"
TITLE  = "Surface Skin Friction Coefficient"
SUBTITLE = "Re = 10^{5} (L=1), M = 0.2"

# --- LOAD GLOBAL STYLE ---
#DATA_DIR = system("echo $OFSCRIPT_DIR")
DATA_DIR = "/home/helios/OpenFOAM/helios-13/run/SCRIPT"
load DATA_DIR . "/TEMPLATE_CASE/10_SCRIPT/POST_TRAITEMENT/GNUPLOT/gnuplot_template.gp"

# --- FILES & LIMITS (your specific data) ---
LAMINAIRE = "09_POST_TRAITEMENT/DATA/OF13_2DZP_20251102_170729_wallShearStressCoefficient.dat"
REF = "06_REFERENCE/cf_plate.dat"

set xrange [0:2]
set yrange [.0:.006]

# --- PLOT --------------------------------------------------------------------
plot \
    LAMINAIRE using 1:(-$2) with lines ls 2 title "Coarse mesh (laminar test)", \
    REF using 1:2      with lines ls 1 title "CFL3D"

# --- END / RESET -------------------------------------------------------------
unset output
reset
