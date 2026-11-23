import base64
import json
import math
import multiprocessing as mp
import os
import platform
import random
import statistics
import time
import uuid
from pathlib import Path

import psutil
from flask import Flask, jsonify, render_template, request, send_from_directory
from PIL import Image

from engine import (
    FORMATS,
    PANIC,
    build_strip,
    burn_worker,
    clamp,
    decode,
    default_image,
    encode,
    img_to_b64,
    pick_indices,
    scar,
    stress_of,
)

app = Flask(__name__)

BASE_DIR = Path(__file__).parent.resolve()
ARCHIVE_DIR = BASE_DIR / "archive"
ARCHIVE_DIR.mkdir(exist_ok=True)
INDEX_FILE = ARCHIVE_DIR / "gallery.json"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/archive/<path:filename>")
def serve_archive(filename):
    return send_from_directory(ARCHIVE_DIR, filename)


@app.route("/api/vitals")
def api_vitals():
    return jsonify({
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent,
        "cores": os.cpu_count() or 1,
        "machine": f"{platform.system()} ({platform.machine()})",
    })


@app.route("/api/run", methods=["POST"])
def api_run():
    gens = int(request.form.get("gens", 24))
    intensity = float(request.form.get("intensity", 0.6))
    heal = float(request.form.get("heal", 0.06))
    enable_scars = request.form.get("scars", "true").lower() == "true"
    mode = request.form.get("mode", "live")
    sim_load = float(request.form.get("simLoad", 75.0))
    profile_name = request.form.get("profileName", "Live Machine")

    if "image" in request.files and request.files["image"].filename:
        img = Image.open(request.files["image"].stream).convert("RGB")
    else:
        img = default_image()

    img.thumbnail((540, 540))
    base = img.copy()

    duty = None
    stop = None
    workers = []

    if mode == "burn":
        duty = mp.Value("d", 0.0)
        stop = mp.Event()
        workers = [
            mp.Process(target=burn_worker, args=(duty, stop), daemon=True)
            for _ in range(os.cpu_count() or 2)
        ]
        for w in workers:
            w.start()

    frames = []
    ledger = []
    period = max(8, gens // 2)

    try:
        psutil.cpu_percent(None)
        for gen in range(gens):
            if duty is not None:
                duty.value = 0.5 + 0.5 * math.sin(2 * math.pi * gen / period - math.pi / 2)

            real_cpu = psutil.cpu_percent(interval=0.12 if mode in ("live", "burn") else None)
            ram = psutil.virtual_memory().percent

            if mode in ("live", "burn"):
                load = real_cpu
            elif mode == "sim_heavy":
                load = clamp(65 + 20 * math.sin(gen * 0.4) + random.uniform(-5, 5), 0, 100)
            elif mode == "sim_panic":
                load = clamp(88 + random.uniform(-4, 12), 0, 100)
            else:
                load = clamp(sim_load + random.uniform(-4, 4), 0, 100)

            t = stress_of(load) * intensity
            fmt = FORMATS[gen % len(FORMATS)]
            comment = f"gen={gen} cpu={real_cpu:.0f} load={load:.0f} ram={ram:.0f}"

            data = encode(img, fmt, t, comment)
            scar_n = 0
            if enable_scars and load >= PANIC:
                data, new_img, scar_n = scar(data, fmt, load)
            else:
                new_img = decode(data)
            img = new_img or img

            frames.append(img.copy())
            ledger.append({
                "gen": gen,
                "format": fmt,
                "cpu": round(real_cpu, 1),
                "load": round(load, 1),
                "ram": round(ram, 1),
                "stress": round(t, 2),
                "bytes": len(data),
                "scar_bytes": scar_n,
            })

            if heal > 0:
                img = Image.blend(img, base, heal)
    finally:
        if stop:
            stop.set()
            for w in workers:
                w.join(timeout=2)
                if w.is_alive():
                    w.terminate()

    selected = pick_indices(len(frames), 6)
    strip_img = build_strip([frames[i] for i in selected])

    summary = {
        "profileName": profile_name,
        "machine": f"{platform.system()} ({platform.machine()}, {os.cpu_count()} cores)",
        "gens": gens,
        "meanLoad": round(statistics.mean(r["load"] for r in ledger), 1),
        "maxLoad": round(max(r["load"] for r in ledger), 1),
        "scarredFrames": sum(1 for r in ledger if r["scar_bytes"] > 0),
        "totalScarBytes": sum(r["scar_bytes"] for r in ledger),
    }

    return jsonify({
        "summary": summary,
        "recipe": {
            "gens": gens,
            "intensity": intensity,
            "heal": heal,
            "scars": enable_scars,
            "mode": mode,
            "simLoad": sim_load,
        },
        "stripImage": img_to_b64(strip_img),
    })


@app.route("/api/gallery", methods=["GET", "POST"])
def api_gallery():
    items = json.loads(INDEX_FILE.read_text()) if INDEX_FILE.exists() else []
    if request.method == "GET":
        return jsonify(items)

    data = request.get_json()
    run_id = uuid.uuid4().hex[:10]
    img_b64 = data["stripImage"].split(",", 1)[1]
    (ARCHIVE_DIR / f"{run_id}.png").write_bytes(base64.b64decode(img_b64))

    entry = {
        "id": run_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "imageUrl": f"/archive/{run_id}.png",
        "summary": data["summary"],
        "recipe": data["recipe"],
    }
    items.insert(0, entry)
    INDEX_FILE.write_text(json.dumps(items, indent=2))
    return jsonify(entry), 201


if __name__ == "__main__":
    mp.freeze_support()
    psutil.cpu_percent(None)
    print("Running at http://127.0.0.1:5050")
    app.run(host="127.0.0.1", port=5050, debug=False)