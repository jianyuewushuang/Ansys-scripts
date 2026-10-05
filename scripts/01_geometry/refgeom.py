import os
BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
"""Locate MAC and its quarter-chord point -> pitching-moment reference centre."""
import numpy as np, re, json

path = BASE + "/data/1.stl"
txt = open(path, "r", errors="ignore").read()
V = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt), dtype=float)
tri = V.reshape(-1, 3, 3)
ymax = V[:, 1].max()

NB = 800
ye = np.linspace(3.55, ymax, NB + 1)
yc, chord, xle, xte = [], [], [], []
for i in range(NB):
    lo, hi = ye[i], ye[i + 1]
    m = (np.abs(tri[:, :, 1]).max(axis=1) >= lo) & (np.abs(tri[:, :, 1]).min(axis=1) <= hi)
    if m.sum() < 2:
        continue
    c = tri[m].reshape(-1, 3)
    cmin, cmax = c[:, 0].min(), c[:, 0].max()
    xle.append(cmin); xte.append(cmax)
    chord.append(cmax - cmin); yc.append((lo + hi) / 2)

yc = np.array(yc); chord = np.array(chord); xle = np.array(xle); xte = np.array(xte)
S_half = np.trapezoid(chord, yc)
MAC = np.trapezoid(chord ** 2, yc) / S_half
x_le_mac = np.trapezoid(chord * xle, yc) / S_half
x_qc = x_le_mac + 0.25 * MAC
S_w = 2 * S_half
span = 2 * ymax

print("=" * 55)
print("  WING GEOMETRY / MOMENT REFERENCE")
print("=" * 55)
print(f"  semi-span fit range   |y| = {yc[0]:.3f} .. {yc[-1]:.3f}")
print(f"  full span             b   = {span:.4f} m")
print(f"  wing area             S_w = {S_w:.4f} m^2")
print(f"  mean aero chord       MAC = {MAC:.4f} m")
print(f"  MAC leading edge      x   = {x_le_mac:.4f} m")
print(f"  MAC quarter chord     x   = {x_qc:.4f} m   <-- moment reference")
print(f"  aspect ratio          AR  = {span**2/S_w:.4f}")
print(f"  taper ratio  ct/cr        = {chord[-1]/chord[0]:.4f}")
print(f"  root chord (fit)          = {chord[0]:.4f} m")
print(f"  tip  chord (fit)          = {chord[-1]:.4f} m")
sw = xte[0] - xle[0]
print(f"  LE sweep (approx)         = {np.degrees(np.arctan((xle[-1]-xle[0])/(yc[-1]-yc[0]))):.2f} deg")

json.dump(dict(span=span, S_w=S_w, MAC=MAC, x_le_mac=x_le_mac, x_qc=x_qc,
               moment_centre=[x_qc, 0.0, 0.0]),
          open(BASE + "/results/refgeom.json", "w"),
          indent=2)
print("\nsaved refgeom.json")
