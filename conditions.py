"""5 km ISA flight conditions + CFD reference values for the UAV."""
import numpy as np, re, json

# ---------- ISA atmosphere at 5 km ----------
h = 5000.0
T0, p0, rho0, a0 = 288.15, 101325.0, 1.225, 340.294
LAPSE = 0.0065
g, R = 9.80665, 287.05287
T = T0 - LAPSE * h
p = p0 * (T / T0) ** (g / (LAPSE * R))
rho = p / (R * T)
a = np.sqrt(1.4 * R * T)

# Sutherland viscosity
mu0, Ts = 1.716e-5, 110.4
mu = mu0 * (T / 273.15) ** 1.5 * (273.15 + Ts) / (T + Ts)

V = 60.0
Mach = V / a
q = 0.5 * rho * V ** 2

print("=" * 62)
print("  FLIGHT CONDITION   —  5 km ISA, V = 60 m/s")
print("=" * 62)
print(f"  Static temperature   T   = {T:10.3f} K")
print(f"  Static pressure      p   = {p:10.2f} Pa")
print(f"  Density              rho = {rho:10.5f} kg/m^3")
print(f"  Speed of sound       a   = {a:10.3f} m/s")
print(f"  Dynamic viscosity    mu  = {mu:10.4e} Pa.s")
print(f"  Mach number          M   = {Mach:10.4f}")
print(f"  Dynamic pressure     q   = {q:10.2f} Pa")

# ---------- reference geometry ----------
txt = open("C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004/1.stl",
           "r", errors="ignore").read()
Vt = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt), dtype=float)
tri = Vt.reshape(-1, 3, 3)
a_ = tri[:, 1] - tri[:, 0]
b_ = tri[:, 2] - tri[:, 0]
n2 = np.cross(a_, b_)
# projected area of triangle onto XY = 0.5*|n_z|.  Top and bottom surfaces both
# project onto the same footprint, so footprint = (sum over all tris)/2
S_total = np.abs(n2[:, 2]).sum() / 4.0

span = Vt[:, 1].max() - Vt[:, 1].min()

# wing planform area by strip integration, |y| from 3.55 (wing root) to tip
NB = 400
ye = np.linspace(3.55, span / 2, NB + 1)
chord = []
yc = []
for i in range(NB):
    lo, hi = ye[i], ye[i + 1]
    m = (np.abs(tri[:, :, 1]).max(axis=1) >= lo) & (np.abs(tri[:, :, 1]).min(axis=1) <= hi)
    if m.sum() < 2:
        chord.append(np.nan); yc.append((lo + hi) / 2); continue
    c = tri[m].reshape(-1, 3)
    chord.append(c[:, 0].max() - c[:, 0].min())
    yc.append((lo + hi) / 2)
chord = np.array(chord); yc = np.array(yc)
ok = ~np.isnan(chord)
S_half = np.trapezoid(chord[ok], yc[ok])
S_wing = 2 * S_half
# mean aerodynamic chord for a tapered wing
MAC = (2.0 / S_wing) * np.trapezoid(chord[ok] ** 2, yc[ok])
# strip-integrated full planform (for cross-check)
S_full_strip = 2 * np.trapezoid(chord[ok], yc[ok])

print("\n" + "=" * 62)
print("  REFERENCE VALUES")
print("=" * 62)
print(f"  Span                  b      = {span:10.4f} m")
print(f"  Length                L      = {Vt[:,0].max()-Vt[:,0].min():10.4f} m")
print(f"  Wing planform area    S_w    = {S_wing:10.4f} m^2   (|y| 3.55..{span/2:.2f})")
print(f"  Mean aero chord       MAC    = {MAC:10.4f} m")
print(f"  Aspect ratio          AR     = {span**2/S_wing:10.4f}")
print(f"  Total planform (all)  S_tot  = {S_total:10.4f} m^2")
print(f"  Wing area / total            = {S_wing/S_total:10.4f}")

Re_MAC = rho * V * MAC / mu
print(f"\n  Reynolds (MAC)        Re     = {Re_MAC:.4e}")
print(f"  Reynolds (span)       Re_b   = {rho*V*span/mu:.4e}")

out = dict(T=T, p=p, rho=rho, a=a, mu=mu, V=V, Mach=Mach, q=q,
           span=span, S_wing=S_wing, MAC=MAC, S_total=S_total, Re=Re_MAC)
json.dump(out, open("C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004/refvalues.json", "w"), indent=2)

print("\n--- example load estimate at CL_w = 0.40 ---")
L = q * S_wing * 0.40
print(f"  Lift = {L:,.0f} N   ->  equivalent mass {L/9.80665:,.0f} kg")
print("\nsaved refvalues.json")
