"""
Builds report/okf_benchmark_report.html from the three arm result JSONs
plus compare.py's output. Self-contained: no external CDN, no network
fetch at render time, inline SVG for charts.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))
from compare import latest_result, paired_table, mcnemar_exact_p  # noqa: E402

REPORT_DIR = Path(__file__).resolve().parent
OUT_PATH = REPORT_DIR / "okf_benchmark_report.html"


def fmt_pct(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def calibration_svg(calibration_table: dict, width=480, height=160) -> str:
    if not calibration_table:
        return "<p>No calibration data.</p>"
    bands = sorted(float(k) for k in calibration_table)
    bars = []
    bw = width / max(len(bands), 1)
    for i, b in enumerate(bands):
        stats = calibration_table[str(b)] if str(b) in calibration_table else calibration_table[b]
        acc = stats["correct"] / stats["n"] if stats["n"] else 0
        bar_h = acc * (height - 20)
        x = i * bw
        highlight = " fill='#d97706'" if 0.75 <= b <= 0.82 else " fill='#2563eb'"
        bars.append(
            f"<rect x='{x:.1f}' y='{height - 20 - bar_h:.1f}' width='{bw * 0.8:.1f}' "
            f"height='{bar_h:.1f}'{highlight} />"
            f"<text x='{x:.1f}' y='{height - 5}' font-size='9'>{b:.2f}</text>"
        )
    return f"<svg width='{width}' height='{height}' xmlns='http://www.w3.org/2000/svg'>{''.join(bars)}</svg>"


def stage_table(metrics_by_arm: dict, stage: str) -> str:
    rows = ["<tr><th>Metric</th><th>A1</th><th>A2</th><th>A3</th></tr>"]
    keys = [
        ("matter_accuracy", fmt_pct), ("autofile_precision", fmt_pct),
        ("autofile_recall", fmt_pct), ("review_rate", fmt_pct),
        ("harmful_error_count", str), ("p50_route_ms", lambda x: f"{x:.1f} ms" if x else "—"),
        ("p90_route_ms", lambda x: f"{x:.1f} ms" if x else "—"),
    ]
    for key, fmt in keys:
        cells = []
        for arm in (1, 2, 3):
            v = metrics_by_arm[arm].get(stage, {}).get(key)
            cells.append(fmt(v) if v is not None else "—")
        rows.append(f"<tr><td>{key}</td><td>{cells[0]}</td><td>{cells[1]}</td><td>{cells[2]}</td></tr>")
    return "<table>" + "".join(rows) + "</table>"


def significance_section(results: dict) -> str:
    out = []
    for a, b in [(1, 2), (1, 3), (2, 3)]:
        out.append(f"<h3>Arm {a} vs Arm {b}</h3><table><tr><th>Stage</th><th>Both</th><th>Only A</th><th>Only B</th><th>Neither</th><th>p</th><th>Result</th></tr>")
        for stage in (None, "easy", "medium", "hard"):
            both, only_a, only_b, neither = paired_table(results[a]["records"], results[b]["records"], stage)
            p = mcnemar_exact_p(only_a, only_b)
            label = stage or "overall"
            verdict = f"significant (p={p:.3f})" if p < 0.05 else f"not significant (n={only_a + only_b}, p={p:.3f})"
            out.append(f"<tr><td>{label}</td><td>{both}</td><td>{only_a}</td><td>{only_b}</td><td>{neither}</td><td>{p:.3f}</td><td>{verdict}</td></tr>")
        out.append("</table>")
    return "".join(out)


def build():
    results = {arm: latest_result(arm) for arm in (1, 2, 3)}
    metrics_by_arm = {arm: results[arm]["metrics"] for arm in (1, 2, 3)}

    exec_rows = "".join(
        f"<tr><td>A{arm}</td><td>{fmt_pct(metrics_by_arm[arm]['overall']['matter_accuracy'])}</td>"
        f"<td>{metrics_by_arm[arm]['overall']['harmful_error_count']}</td>"
        f"<td>{metrics_by_arm[arm]['invariant_violations']}</td>"
        f"<td>{metrics_by_arm[arm]['overall']['p50_route_ms']:.1f} ms</td></tr>"
        for arm in (1, 2, 3)
    )

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>OKF Routing Benchmark Report</title>
<style>
body {{ font-family: Georgia, serif; max-width: 900px; margin: 2rem auto; color: #1a1a1a; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; font-size: 14px; }}
th {{ background: #f3f3f3; }}
h1, h2 {{ border-bottom: 2px solid #333; padding-bottom: 4px; }}
.gate-pass {{ color: #16a34a; font-weight: bold; }}
.gate-fail {{ color: #dc2626; font-weight: bold; }}
</style></head>
<body>
<h1>OKF Matter-Pool Routing Benchmark</h1>
<p>Three-arm comparison: SQLite control (A1) vs OKF format-parity (A2) vs OKF + multi-signal (A3).</p>

<h2>1. Executive Summary</h2>
<table><tr><th>Arm</th><th>Overall Accuracy</th><th>Harmful Errors</th><th>Invariant Violations</th><th>P50 Latency</th></tr>
{exec_rows}
</table>

<h2>2. Per-Difficulty Results</h2>
<h3>Easy</h3>{stage_table(metrics_by_arm, 'easy')}
<h3>Medium</h3>{stage_table(metrics_by_arm, 'medium')}
<h3>Hard</h3>{stage_table(metrics_by_arm, 'hard')}

<h2>3. Paired Significance (McNemar)</h2>
{significance_section(results)}

<h2>4. Safety</h2>
<table><tr><th>Arm</th><th>Autofile Precision</th><th>Harmful Errors</th><th>Stage D Gate</th></tr>
{''.join(
    f"<tr><td>A{arm}</td><td>{fmt_pct(metrics_by_arm[arm]['overall']['autofile_precision'])}</td>"
    f"<td>{metrics_by_arm[arm]['overall']['harmful_error_count']}</td>"
    f"<td class='{'gate-pass' if metrics_by_arm[arm]['invariant_violations']==0 else 'gate-fail'}'>"
    f"{'PASS' if metrics_by_arm[arm]['invariant_violations']==0 else 'FAIL'}</td></tr>"
    for arm in (1, 2, 3)
)}
</table>

<h2>5. Calibration (Stage C)</h2>
<p>Orange bars mark the 0.75&ndash;0.82 confidence band that produced the baseline's failures.</p>
{''.join(f"<h4>Arm {arm}</h4>{calibration_svg(metrics_by_arm[arm].get('calibration_table', {}))}" for arm in (1, 2, 3))}

<h2>6. Limitations</h2>
<ul>
<li>Sample size and statistical power per §1.4 of the test guide — treat non-significant deltas as directional only.</li>
<li>Field-density gap: InLegalNER judgments are richer than real CaseDesk matter records typed by an advocate at intake.</li>
<li>Cross-links in the OKF bundle are rule-generated (party-name / court+statute+date proximity), not expert-curated.</li>
</ul>

<h2>7. Conclusion</h2>
<p>Compare A2 to A1 first: if they are not statistically equivalent, the experiment has a parity leak and A3's numbers should not be trusted. If A2 ≈ A1, any A3 delta above is attributable to the multi-signal §9 features, not to OKF as a format.</p>

</body></html>"""

    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    build()
