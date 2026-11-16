"""J0 : rendu hors écran de l'Aim9, débit 1 vue / 3 vues, 1080p / 4K."""
import json
import os
import sys
import time

import numpy as np
import pyvista as pv
import trimesh

stl, sortie = sys.argv[1], sys.argv[2]
pv.OFF_SCREEN = True
m = trimesh.load(stl)
mesh = pv.wrap(m)
mesh.points -= np.array([38.1011, 0.0, 0.0])   # origine au culot
res = {"backend": os.environ.get("VTK_DEFAULT_OPENGL_WINDOW", "defaut"),
       "display": os.environ.get("DISPLAY", "")}
def plotter(L, H):
    p = pv.Plotter(off_screen=True, window_size=(L, H))
    p.add_mesh(mesh, color="#d9d9d9", smooth_shading=True, pbr=True, metallic=0.6, roughness=0.35)
    p.set_background("#9cc3e6", top="#0b2a55")
    p.add_mesh(pv.Plane(center=(0, 0, -15), direction=(0, 0, 1), i_size=400, j_size=400), color="#3b4a2f")
    return p
p = plotter(1920, 1080)

p.camera_position = [(-60, -55, 20), (-19, 0, 0), (0, 0, 1)]
p.screenshot(os.path.join(sortie, "aim9_1080p.png")); res["gl"] = [l for l in p.ren_win.ReportCapabilities().splitlines() if "renderer" in l.lower() or "version" in l.lower()][:3]
def debit(L, H, n=30):
    p = plotter(L, H); p.show(auto_close=False, interactive=False)
    t0 = time.perf_counter()
    for i in range(n):
        a = 2 * np.pi * i / n
        p.camera_position = [(-19 + 60 * np.cos(a), 60 * np.sin(a), 20), (-19, 0, 0), (0, 0, 1)]
        img = p.screenshot(return_img=True)
    dt = (time.perf_counter() - t0) / n
    p.close(); return round(1000 * dt, 1), img.shape
res["ms_1080p"], _ = debit(1920, 1080)
res["ms_4K"], shp = debit(3840, 2160, 10)
res["ms_540p_incrustation"], _ = debit(540, 304)
res["forme_4K"] = list(shp)
print(json.dumps(res, ensure_ascii=False, indent=1))
