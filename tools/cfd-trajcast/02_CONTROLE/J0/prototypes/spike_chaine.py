"""J0 : cascadio (STEP), panneau matplotlib, encodage imageio-ffmpeg en flux."""
import io
import sys
import time
import json
import subprocess
import numpy as np
import trimesh
import cascadio
import imageio_ffmpeg
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
res = {}
for f in ["/usr/share/opencascade/data/step/screw.step", "/usr/share/opencascade/data/step/linkrods.step"]:
    t0 = time.perf_counter(); glb = cascadio.load(open(f, "rb").read(), file_type="step")
    sc = trimesh.load(io.BytesIO(glb), file_type="glb"); m = sc.to_mesh() if hasattr(sc, "to_mesh") else sc
    res[f.split("/")[-1]] = {"s": round(time.perf_counter() - t0, 2), "faces": len(m.faces), "boite": np.round(m.extents, 2).tolist()}
# panneau télémétrie 600x1080 en blitting
fig, axs = plt.subplots(4, 1, figsize=(6, 10.8), dpi=100)
t = np.linspace(0, 30, 1800); y = [np.sin(t / 5 + k) for k in range(4)]
lignes = [a.plot([], [], lw=2)[0] for a in axs]
for a, yy in zip(axs, y): a.set_xlim(0, 30); a.set_ylim(yy.min() - .1, yy.max() + .1)
fig.canvas.draw(); fonds = [fig.canvas.copy_from_bbox(a.bbox) for a in axs]
t0 = time.perf_counter()
for i in range(0, 1800, 3):
    for a, l, f, yy in zip(axs, lignes, fonds, y):
        fig.canvas.restore_region(f); l.set_data(t[:i], yy[:i]); a.draw_artist(l); fig.canvas.blit(a.bbox)
    img = np.asarray(fig.canvas.buffer_rgba())
res["ms_panneau_blit"] = round(1000 * (time.perf_counter() - t0) / 600, 2)
# encodage 600 images 1080p
W, H = 1920, 1080
w = imageio_ffmpeg.write_frames(sys.argv[1], (W, H), fps=60, codec="libx264", pix_fmt_out="yuv420p",
                                quality=None, output_params=["-crf", "18", "-preset", "medium"])
w.send(None); base = np.random.default_rng(0).integers(0, 255, (H, W, 3), np.uint8) // 4
t0 = time.perf_counter()
for i in range(600):
    fr = base.copy(); fr[:, (3 * i) % W] = 255; w.send(fr)
w.close(); res["ms_encodage_1080p"] = round(1000 * (time.perf_counter() - t0) / 600, 2)
out = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", sys.argv[1]], capture_output=True, text=True).stderr
res["ffmpeg"] = [l.strip() for l in out.splitlines() if "Video:" in l or "Duration" in l]
print(json.dumps(res, ensure_ascii=False, indent=1))
