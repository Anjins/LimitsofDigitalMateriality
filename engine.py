import base64
import io
import os
import platform
import random
import subprocess
import time

import psutil
from PIL import Image, ImageFile, ImageOps

ImageFile.LOAD_TRUNCATED_IMAGES = True

CALM = 30
PANIC = 80
FORMATS = ["JPEG", "GIF", "BMP"]


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def stress_of(load):
    return clamp((load - CALM) / (100 - CALM))


def burn_worker(duty, stop):
    while not stop.is_set():
        d = duty.value
        t0 = time.perf_counter()
        x = 1.0001
        while time.perf_counter() - t0 < 0.1 * d:
            x = (x * 1.000001) % 7.0
        time.sleep(0.1 * (1 - d))


def encode(img, fmt, t, comment):
    img = img.convert("RGB")
    w, h = img.size

    if t > 0.6:
        f = lerp(1.0, 0.5, (t - 0.6) / 0.4)
        small = img.resize((max(8, int(w * f)), max(8, int(h * f))), Image.BILINEAR)
        img = small.resize((w, h), Image.NEAREST)

    buf = io.BytesIO()
    if fmt == "JPEG":
        quality = 95 if t == 0 else int(lerp(92, 30, t))
        img.save(
            buf,
            "JPEG",
            quality=quality,
            subsampling=0 if t < 0.5 else 2,
            comment=comment.encode("ascii", "replace"),
        )
    elif fmt == "GIF":
        colors = 256 if t == 0 else max(24, int(256 * (1 - t) ** 1.5))
        dither = Image.Dither.FLOYDSTEINBERG if t < 0.85 else Image.Dither.NONE
        img.quantize(colors=colors, dither=dither).save(
            buf,
            "GIF",
            comment=comment.encode("ascii", "replace"),
        )
    else:
        if t > 0:
            img = ImageOps.posterize(img, max(4, 8 - int(t * 4)))
            r, g, b = img.split()
            shift = int(t * w * 0.006)
            img = Image.merge(
                "RGB",
                (
                    r,
                    g.transform(g.size, Image.AFFINE, (1, 0, shift, 0, 1, 0)),
                    b.transform(b.size, Image.AFFINE, (1, 0, -shift, 0, 1, 0)),
                ),
            )
        img.save(buf, "BMP")

    return buf.getvalue()


def decode(data):
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        return img.convert("RGB")
    except Exception:
        return None


def system_log_line():
    cmds = {
        "Linux": ["journalctl", "-n", "3", "--no-pager"],
        "Darwin": ["log", "show", "--last", "10s", "--style", "compact"],
    }.get(platform.system())

    if not cmds:
        return ""

    try:
        out = subprocess.run(cmds, capture_output=True, text=True, timeout=1.0).stdout
        lines = [line for line in out.splitlines() if line.strip()]
        return random.choice(lines)[:120] if lines else ""
    except Exception:
        return ""


def running_apps(k=5):
    procs = []
    for p in psutil.process_iter(["name", "memory_percent"]):
        try:
            procs.append((p.info["memory_percent"] or 0, p.info["name"] or "?"))
        except Exception:
            pass
    procs.sort(reverse=True)
    return [name for _, name in procs[:k]]


def build_payload(load):
    size = int(lerp(12, 160, clamp((load - PANIC) / (100 - PANIC))))
    apps = ",".join(running_apps())
    text = f"[{time.strftime('%H:%M:%S')}] apps={apps} | {system_log_line()} | "
    raw = text.encode("ascii", "replace") + os.urandom(size)
    return raw[:size]


def body_offset(data, fmt):
    if fmt == "JPEG":
        i = data.find(b"\xff\xda")
        if i >= 0:
            return i + 2 + int.from_bytes(data[i + 2 : i + 4], "big")
        return 600
    if fmt == "BMP":
        return int.from_bytes(data[10:14], "little")
    return min(900, len(data) // 3)


def splice(data, fmt, payload):
    start = body_offset(data, fmt)
    end = len(data) - 4
    if end - start < 16:
        return data
    payload = payload[: end - start]
    if fmt == "JPEG":
        payload = payload.replace(b"\xff", b"\xfe")
    pos = random.randrange(start, max(start + 1, end - len(payload)))
    out = bytearray(data)
    out[pos : pos + len(payload)] = payload
    return bytes(out)


def scar(data, fmt, load):
    payload = build_payload(load)
    for _ in range(4):
        scarred = splice(data, fmt, payload)
        img = decode(scarred)
        if img is not None:
            return scarred, img, len(payload)
        payload = payload[: len(payload) // 2]
        if not payload:
            break
    return data, decode(data), 0


def img_to_b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def build_strip(images):
    w = sum(im.width for im in images)
    h = max(im.height for im in images)
    strip = Image.new("RGB", (w, h), (255, 255, 255))
    x = 0
    for im in images:
        strip.paste(im, (x, 0))
        x += im.width
    return strip


def default_image():
    img = Image.new("RGB", (480, 480), (20, 24, 36))
    px = img.load()
    for y in range(480):
        for x in range(480):
            r = int(255 * x / 480)
            g = int(255 * y / 480)
            b = 150 if (x % 32 == 0 or y % 32 == 0) else 75
            px[x, y] = (r, g, b)
    return img


def pick_indices(total, count=6):
    if total <= count:
        return list(range(total))
    return sorted({int(i * (total - 1) / (count - 1)) for i in range(count)})