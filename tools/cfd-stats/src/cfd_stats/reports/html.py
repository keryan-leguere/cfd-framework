"""HTML report generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cfd_stats.reports.summary import results_to_json

_CSS = """\
:root { --bg: #1e1e2e; --fg: #cdd6f4; --accent: #89b4fa; --green: #a6e3a1;
        --yellow: #f9e2af; --red: #f38ba8; --surface: #313244; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Inter', system-ui, sans-serif; background: var(--bg);
       color: var(--fg); padding: 2rem; line-height: 1.6; }
h1 { color: var(--accent); margin-bottom: 1rem; }
h2 { color: var(--accent); margin: 1.5rem 0 0.5rem; border-bottom: 1px solid var(--surface); padding-bottom: 0.3rem; }
table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
th, td { padding: 0.5rem 0.8rem; text-align: left; border: 1px solid var(--surface); }
th { background: var(--surface); color: var(--accent); }
.converged { color: var(--green); font-weight: bold; }
.periodic  { color: var(--accent); font-weight: bold; }
.transient { color: var(--yellow); font-weight: bold; }
.diverging { color: var(--red); font-weight: bold; }
.panel { background: var(--surface); border-radius: 8px; padding: 1rem; margin: 1rem 0; }
.rec { padding: 0.5rem; border-left: 4px solid var(--accent); margin: 0.5rem 0; background: var(--surface); border-radius: 4px; }
"""


def save_html(results: dict, path: str | Path, *, input_file: str = "") -> Path:
    """Render a standalone HTML report.

    Parameters
    ----------
    results : dict
        Full pipeline output from :class:`AutomaticDetector`.
    path : str or Path
        Destination HTML file.
    input_file : str
        Original data filename (shown in the header).

    Returns
    -------
    Path
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    payload = results_to_json(results, input_file=input_file)
    ga = payload.get("global", {})
    per_coeff = payload.get("per_coefficient", {})

    parts: list[str] = [
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>CFD Statistics Report</title>",
        f"<style>{_CSS}</style></head><body>",
        "<h1>CFD Statistics Report</h1>",
        f"<p>Input: <code>{input_file or '—'}</code></p>",
    ]

    # Global summary
    regime = ga.get("regime", "?")
    parts.append("<div class='panel'>")
    parts.append(f"<b>Overall regime:</b> <span class='{regime}'>{regime}</span><br>")
    parts.append(f"<b>All converged:</b> {ga.get('all_converged', '?')}<br>")
    parts.append(f"<b>Quality score:</b> {ga.get('quality_score', '?')}<br>")
    parts.append(f"<b>Recommendation:</b> {ga.get('recommendation', '')}")
    parts.append("</div>")

    # Summary table
    parts.append("<h2>Per-coefficient summary</h2>")
    parts.append("<table><tr><th>Coefficient</th><th>Regime</th><th>Mean</th>")
    parts.append("<th>Std</th><th>Converged</th><th>Quality</th></tr>")
    for name, data in per_coeff.items():
        r = data.get("regime", {})
        m = data.get("moments", {})
        c = data.get("convergence", {})
        css = r.get("regime", "")
        parts.append(
            f"<tr><td>{name}</td>"
            f"<td class='{css}'>{r.get('regime', '?')}</td>"
            f"<td>{_hfmt(m.get('mean'))}</td>"
            f"<td>{_hfmt(m.get('std'))}</td>"
            f"<td>{c.get('is_converged', '?')}</td>"
            f"<td>{r.get('quality_score', '?')}</td></tr>"
        )
    parts.append("</table>")

    # Detailed sections
    for name, data in per_coeff.items():
        parts.append(f"<h2>{name}</h2>")
        parts.append(_detail_panel(data))

    parts.append("</body></html>")

    out.write_text("\n".join(parts))
    return out


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _hfmt(val: Any) -> str:
    if val is None:
        return "—"
    if isinstance(val, float):
        if abs(val) < 1e-3 or abs(val) > 1e6:
            return f"{val:.6e}"
        return f"{val:.6f}"
    return str(val)


def _detail_panel(data: dict) -> str:
    parts: list[str] = ["<div class='panel'>"]

    conv = data.get("convergence", {})
    parts.append("<b>Convergence</b><br>")
    parts.append(f"Rate: {conv.get('convergence_rate', '?')} | ")
    parts.append(f"Cauchy: {_hfmt(conv.get('cauchy_criterion'))} | ")
    parts.append(f"Plateau: {conv.get('plateau_iterations', '?')} iters<br><br>")

    per = data.get("periodicity", {})
    parts.append("<b>Periodicity</b><br>")
    parts.append(f"Detected: {per.get('detected', '?')} | Period: {_hfmt(per.get('period'))} | ")
    parts.append(f"N periods: {per.get('n_periods', '?')} | Quality: {per.get('quality_flag', '?')}<br><br>")

    m = data.get("moments", {})
    if m:
        parts.append("<b>Moments</b><br>")
        parts.append(f"Mean: {_hfmt(m.get('mean'))} | Std: {_hfmt(m.get('std'))} | ")
        parts.append(f"Skewness: {_hfmt(m.get('skewness'))} | Kurtosis: {_hfmt(m.get('kurtosis'))}<br>")

    parts.append("</div>")
    return "\n".join(parts)
