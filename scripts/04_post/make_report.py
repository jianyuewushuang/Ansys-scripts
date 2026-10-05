"""Build the HTML summary report from results/."""
import os
import json
import html

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
OUT = os.path.join(BASE, "results")

FORCES = None
p = os.path.join(OUT, "forces.json")
if os.path.exists(p):
    FORCES = json.load(open(p))

AOAS = [0, 4, 8, 12]
PER_AOA = [
    ("cp3d_surf_aoa%d_planform.png", "Surface Cp - planform"),
    ("cp3d_surf_aoa%d_side.png", "Surface Cp - side"),
    ("cp3d_surf_aoa%d_front.png", "Surface Cp - front 3/4"),
    ("cp_upper_lower_aoa%d.png", "Upper / lower surface Cp"),
    ("sym_fields_aoa%d.png", "Symmetry plane: |V| and Cp"),
    ("sym_streamlines_aoa%d.png", "Streamlines on the symmetry plane"),
    ("vortex3d_aoa%d.png", "Tip-vortex streamlines (3D)"),
    ("wake_xsections_aoa%d.png", "Wake cross-sections"),
    ("wake_horizontal_aoa%d.png", "Horizontal plane wake"),
]
GLOBAL = [("aero_coefficients.png", "Aerodynamic coefficients"),
          ("pitch_moment.png", "Pitching moment"),
          ("residuals.png", "Convergence history")]


def img(name, cap):
    f = os.path.join(OUT, name)
    if not os.path.exists(f):
        return ""
    return ('<figure><img src="%s" loading="lazy"><figcaption>%s</figcaption>'
            '</figure>' % (name, html.escape(cap)))


rows = ""
if FORCES:
    for r in FORCES:
        rows += ("<tr><td>%g&deg;</td><td>%.4f</td><td>%.4f</td>"
                 "<td>%.3f</td><td>%s</td><td>%s</td></tr>"
                 % (r["aoa"], r.get("CL") or 0, r.get("CD") or 0,
                    r.get("L_over_D") or 0,
                    ("%.4f" % r["CM"]) if r.get("CM") else "&ndash;",
                    ("%.0f" % r["L_N"]) if r.get("L_N") else "&ndash;"))

body = []
for a in AOAS:
    sec = "".join(img(t % a, c) for t, c in PER_AOA)
    if not sec:
        continue
    body.append("<h2>Angle of attack %g&deg;</h2>%s" % (a, sec))

glob = "".join(img(n, c) for n, c in GLOBAL)

CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
margin:0;background:#0f1116;color:#e6e8ee}
header{padding:28px 32px;background:linear-gradient(135deg,#1b2130,#243049)}
h1{margin:0 0 6px;font-size:24px}h2{font-size:19px;margin:34px 0 10px;
border-left:4px solid #4f8ef7;padding-left:10px}
.sub{color:#9aa3b2;font-size:13px}
main{padding:8px 32px 60px}
figure{margin:14px 0;background:#161a23;border:1px solid #232a37;
border-radius:10px;padding:10px}
figure img{width:100%;display:block;border-radius:6px}
figcaption{color:#9aa3b2;font-size:12px;margin-top:8px}
table{border-collapse:collapse;margin:14px 0;font-size:14px}
th,td{border:1px solid #2b3342;padding:7px 14px;text-align:right}
th{background:#1d2432;color:#cdd4e0}
td:first-child,th:first-child{text-align:left}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(560px,1fr));
gap:14px}
.note{background:#1a2130;border-left:3px solid #d9a441;padding:12px 16px;
border-radius:6px;color:#c6cede;font-size:13px;line-height:1.65}
"""

doc = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>UAV CFD report</title><style>
/* css */
</style></head><body>
<header><h1>UAV external aerodynamics &mdash; CFD report</h1>
<div class="sub">ANSYS Fluent 2026 R1 &bull; steady RANS k&ndash;&omega; SST &bull;
5 km ISA, V = 60 m/s, Ma = 0.187, Re(MAC) = 1.14&times;10<sup>7</sup><br>
S<sub>ref</sub> = 65.34 m&sup2;, MAC = 4.20 m, moment ref. at quarter-chord
x = 7.93 m &bull; mesh 318k poly-hexcore cells</div></header>
<main>
<h2>Summary</h2>
__TABLE__
<h2>Global results</h2><div class="grid">__GLOB__</div>
__BODY__
<h2>Model notes &amp; limitations</h2>
<div class="note">
Geometry is a faceted STL that had to be repaired (the upload contained four
mutually intersecting closed shells): a voxel union + marching-cubes pass
produced a single watertight solid (174.7 m&sup3;, 262k facets) which is what
was actually meshed.<br><br>
The volume mesh is <b>poly-hexcore without boundary-layer prisms</b>
(318k cells in the fluid region; median wall y&plus; &asymp; 940, i.e. wall
functions). Net effect: <b>drag is over-predicted</b> (roughly 2-3x versus a
properly resolved boundary layer), while lift, the lift-curve slope and the
pressure field are much less sensitive. Read the C<sub>L</sub>&ndash;&alpha;
slope and the pressure/vortex visualisations as the quantitative result, and
treat C<sub>D</sub> as an upper bound.<br><br>
Two separate attempts were made to add prisms. (1) Fluent's watertight
<code>add_boundary_layers</code> task accepts every parameter and logs
"writing boundary layer flags" yet the volume mesher returns a byte-identical
prism-free mesh for all 11 parameter combinations tried - the task is inert
in this 26R1 build. (2) ANSYS Prime Mesh (installed alongside Fluent) does
generate prisms and brought the median y&plus; to <b>110</b>, but the result
carries a minimum orthogonal quality of 3.7&times;10<sup>-4</sup> and a
maximum aspect ratio of 2.6&times;10<sup>4</sup> (prisms extruded off the
far-field box, which cannot be excluded by scope), and the solver diverges on
it. So the wall-function mesh shown here is what the toolchain can currently
deliver; a converged prism solution needs either the GUI-driven mesher or a
larger cell licence.<br><br>
Turbulence: steady RANS k-&omega; SST, ideal gas, pressure far field at
5 km ISA. Coupled solver with explicit relaxation reduced to 0.4 / 0.5 -
the Fluent default (0.75) diverges for this low-Mach compressible case.<br><br>
Convergence: the scaled continuity residual plateaus at O(1-10) rather than
dropping to machine level, but the integrated loads are stationary to &lt;1%
over the last 150 iterations, the domain-mean pressure matches the far-field
static pressure to 0.01% (54025 vs 54019.9 Pa) and the side force on this
symmetric airframe stays below 0.5% of lift - i.e. the solution is physically
consistent.
</div>
</main></body></html>
"""

table = ("<table><tr><th>&alpha;</th><th>C<sub>L</sub></th><th>C<sub>D</sub></th>"
         "<th>L/D</th><th>C<sub>M</sub></th><th>L [N]</th></tr>" + rows +
         "</table>") if rows else "<p>No force data.</p>"

doc = (doc.replace("__TABLE__", table)
          .replace("__GLOB__", glob)
          .replace("__BODY__", "".join(body))
          .replace("/* css */", CSS))

fn = os.path.join(OUT, "report.html")
open(fn, "w", encoding="utf-8").write(doc)
print("saved", fn)
