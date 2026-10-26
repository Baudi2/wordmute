"""The WordMute brag video, drawn frame by frame with QPainter — every
frame is a pure function of time — and piped to ffmpeg.

    python scripts/brag_video/stage_review.py   # UI material
    python scripts/brag_video/render.py stills  # check frames
    python scripts/brag_video/render.py video   # brag-output/work/video_silent.mp4
    python scripts/brag_video/mix.py            # + music & SFX -> brag-output/brag.mp4
    (then the poster: see scripts/brag_video/README.md)

Timeline, palette and copy follow scripts/brag_video/brag-plan.md; cuts
sit on the beat grid of the chosen track (114.84 BPM)."""

import json
import math
import os
import subprocess
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF,
                           QGuiApplication, QImage, QPainter, QPainterPath,
                           QPen, QPixmap, QPolygonF)

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "brag-output" / "work"     # stage_review.py fills it
W, H, FPS = 1920, 1080, 30
DURATION = 21.6

# the site's palette (docs/index.html :root)
BG, PANEL, LINE = QColor("#14161a"), QColor("#1b1e24"), QColor("#2a2e36")
TEXT, DIM = QColor("#e9e7e2"), QColor("#9096a0")
AMBER, MUTE, INK = QColor("#e8a33d"), QColor("#e5484d"), QColor("#17130a")
AMBER_SOFT, MUTE_SOFT = QColor(232, 163, 61, 31), QColor(229, 72, 77, 26)

# scene cuts (seconds) — on the beat grid of vol-11
T_REVEAL, T_QUEUE, T_REVIEW, T_LINK, T_LOCAL, T_OUTRO = (
    3.70, 6.86, 10.54, 13.70, 16.34, 18.96)
CUTS = (T_REVEAL, T_QUEUE, T_REVIEW, T_LINK, T_LOCAL, T_OUTRO)
T_MUTE = 1.60            # the hook's word drops out
T_CLICK = 12.12          # the review checkbox is clicked
T_TOAST = 8.96

app = QGuiApplication(sys.argv)
for ttf in (ROOT / "wordmute_app/resources/theme/fonts").glob("Inter-*.ttf"):
    QFontDatabase.addApplicationFont(str(ttf))


def font(size, weight=QFont.Weight.Normal, family="Inter"):
    f = QFont(family)
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


MONO = "Consolas"


# ------------------------------------------------------------------ easing
def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    x = clamp(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def rise(t, start, dur=0.4, dy=28):
    """(alpha, y offset) for an element that fades up at `start`."""
    k = ease_out((t - start) / dur)
    return k, (1 - k) * dy


def pop(t, start, dur=0.3):
    """(alpha, scale) for a chip that pops in with a little overshoot."""
    x = clamp((t - start) / dur)
    k = ease_out(x)
    scale = 0.8 + 0.2 * k + 0.06 * math.sin(math.pi * x) * (1 - x)
    return k, scale


# --------------------------------------------------------------- material
def load(name, width=None):
    pm = QPixmap(str(WORK / name))
    if width:
        pm = pm.scaledToWidth(width, Qt.SmoothTransformation)
    return pm


QUEUE = load("queue.png", 1500)
REVIEW_A = load("review_a.png", 1500)
REVIEW_B = load("review_b.png", 1500)
ADDURL = load("addurl.png", 1240)
TOAST = load("toast.png", 700)
META = json.load(open(WORK / "review_meta.json"))
REVIEW_SCALE = 1500 / QPixmap(str(WORK / "review_a.png")).width()


# ----------------------------------------------------------------- drawing
def text_width(f, s):
    return QFontMetricsF(f).horizontalAdvance(s)


def draw_text(p, x, y, s, f, color, align="left", alpha=1.0):
    """Baseline at y."""
    p.setFont(f)
    c = QColor(color)
    c.setAlphaF(c.alphaF() * clamp(alpha))
    p.setPen(c)
    w = text_width(f, s)
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    p.drawText(QPointF(x, y), s)
    return w


def rounded(p, rect, radius, fill=None, stroke=None, width=1.0, alpha=1.0):
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    if fill is not None:
        c = QColor(fill)
        c.setAlphaF(c.alphaF() * alpha)
        p.fillPath(path, c)
    if stroke is not None:
        c = QColor(stroke)
        c.setAlphaF(c.alphaF() * alpha)
        p.setPen(QPen(c, width))
        p.drawPath(path)


def draw_pixmap_rounded(p, pm, x, y, radius=12, alpha=1.0, scale=1.0,
                        anchor=None):
    """A UI window: rounded, bordered, optionally zoomed about anchor."""
    p.save()
    p.setOpacity(clamp(alpha))
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    if scale != 1.0:
        ax, ay = anchor or (x + pm.width() / 2, y)
        p.translate(ax, ay)
        p.scale(scale, scale)
        p.translate(-ax, -ay)
    rect = QRectF(x, y, pm.width(), pm.height())
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.setClipPath(path)
    p.drawPixmap(QPointF(x, y), pm)
    p.setClipping(False)
    p.setPen(QPen(QColor("#3a3e48"), 2))
    p.drawPath(path)
    p.restore()


def logo_mark(p, x, y, size, alpha=1.0):
    """The site's mark: amber rounded square, four dark bars (viewBox 14)."""
    p.save()
    p.setOpacity(clamp(alpha))
    rounded(p, QRectF(x, y, size, size), size * 0.23, fill=AMBER)
    u = size / 14
    p.setPen(Qt.NoPen)
    p.setBrush(INK)
    for bx, by, bw, bh in ((1, 5, 2, 4), (4.5, 2, 2, 10), (8, 6, 2, 2),
                           (11.5, 4, 2, 6)):
        p.drawRoundedRect(QRectF(x + bx * u, y + by * u, bw * u, bh * u),
                          u, u)
    p.restore()


def chip(p, cx, cy, s, t, start, f=None, fill=PANEL, stroke=LINE,
         color=TEXT, pad=26, height=56):
    """A pill centred at (cx, cy), popping in at `start`. Returns width."""
    f = f or font(28, QFont.Weight.Medium)
    alpha, scale = pop(t, start)
    if alpha <= 0:
        return text_width(f, s) + 2 * pad
    w = text_width(f, s) + 2 * pad
    p.save()
    p.setOpacity(alpha)
    p.translate(cx, cy)
    p.scale(scale, scale)
    rounded(p, QRectF(-w / 2, -height / 2, w, height), height / 2,
            fill=fill, stroke=stroke)
    draw_text(p, 0, QFontMetricsF(f).capHeight() / 2, s, f, color, "center")
    p.restore()
    return w


def chip_row(p, labels, t, starts, cy, gap=18, **kw):
    f = kw.get("f") or font(28, QFont.Weight.Medium)
    pad = kw.get("pad", 26)
    widths = [text_width(f, s) + 2 * pad for s in labels]
    total = sum(widths) + gap * (len(labels) - 1)
    x = W / 2 - total / 2
    for s, start, w in zip(labels, starts, widths):
        chip(p, x + w / 2, cy, s, t, start, **kw)
        x += w + gap


def cursor(p, x, y, alpha=1.0, pressed=0.0):
    p.save()
    p.setOpacity(clamp(alpha))
    p.setRenderHint(QPainter.Antialiasing)
    if pressed > 0:
        ring = QColor(AMBER)
        ring.setAlphaF(0.6 * (1 - pressed))
        p.setPen(QPen(ring, 3))
        p.setBrush(Qt.NoBrush)
        r = 10 + 26 * pressed
        p.drawEllipse(QPointF(x, y), r, r)
    pts = [(0, 0), (0, 22), (6, 17), (10, 26), (14, 24), (10, 15), (17, 15)]
    poly = QPolygonF([QPointF(x + px * 1.3, y + py * 1.3) for px, py in pts])
    p.setPen(QPen(QColor("#111318"), 2))
    p.setBrush(QColor("#f4f4f6"))
    p.drawPolygon(poly)
    p.restore()


# ------------------------------------------------------------------ scenes
WORDS = ["…дальше", "по", "сюжету", "появляется", "[слово],", "и", "герой",
         "уходит…"]
BAD = 4                                   # index of the word that drops out
BARS = 60
MUTED_FROM, MUTED_TO = 0.47, 0.57         # the word's share of the wave


def scene_hook(p, t):
    card = QRectF(210, 270, 1500, 500)
    rounded(p, card, 16, fill=PANEL, stroke=LINE)
    mono = font(20, QFont.Weight.Normal, MONO)
    draw_text(p, card.left() + 28, card.top() + 44,
              "АУДИОДОРОЖКА · ПРЕДПРОСМОТР ОБРАБОТКИ", mono, DIM)
    # legend
    lx = card.right() - 28
    for label, color in (("заглушено", MUTE), ("речь", AMBER)):
        w = text_width(mono, label)
        draw_text(p, lx, card.top() + 44, label, mono, DIM, "right")
        p.fillRect(QRectF(lx - w - 20, card.top() + 30, 12, 12), color)
        lx -= w + 44
    # the wave
    inner = QRectF(card.left() + 28, card.top() + 92, card.width() - 56, 230)
    gap = 4
    bw = (inner.width() - gap * (BARS - 1)) / BARS
    playhead = clamp(t / 3.45)
    collapse = ease_out((t - T_MUTE) / 0.22)
    for i in range(BARS):
        frac = i / (BARS - 1)
        h = 14 + abs(math.sin(i * 0.9) * 46 + math.sin(i * 0.23) * 24)
        h *= 2.5
        muted = MUTED_FROM <= frac <= MUTED_TO
        if muted:
            h = h + (6 - h) * collapse
            color = QColor(AMBER) if collapse <= 0 else QColor(
                int(AMBER.red() + (MUTE.red() - AMBER.red()) * collapse),
                int(AMBER.green() + (MUTE.green() - AMBER.green()) * collapse),
                int(AMBER.blue() + (MUTE.blue() - AMBER.blue()) * collapse))
        else:
            color = QColor(AMBER)
        color.setAlphaF(0.88 if frac <= playhead else 0.38)
        x = inner.left() + i * (bw + gap)
        y = inner.center().y() - h / 2
        rounded(p, QRectF(x, y, bw, h), 3, fill=color)
    # playhead
    px = inner.left() + playhead * inner.width()
    p.setPen(QPen(QColor(233, 231, 226, 200), 2))
    p.drawLine(QPointF(px, inner.top() - 6), QPointF(px, inner.bottom() + 6))
    # «заглушено» tag over the muted stretch
    if collapse > 0:
        k, dy = rise(t, T_MUTE, 0.3, 14)
        f = font(22, QFont.Weight.DemiBold)
        s = "заглушено"
        w = text_width(f, s) + 36
        cx = inner.left() + (MUTED_FROM + MUTED_TO) / 2 * inner.width()
        rounded(p, QRectF(cx - w / 2, inner.top() - 50 + dy, w, 40), 20,
                fill=MUTE_SOFT, stroke=MUTE, alpha=k)
        draw_text(p, cx, inner.top() - 22 + dy, s, f, MUTE, "center", k)
    # the subtitle line, lit word by word along the playhead
    f = font(44, QFont.Weight.Medium)
    widths = [text_width(f, w_) for w_ in WORDS]
    space = text_width(f, " ")
    total = sum(widths) + space * (len(WORDS) - 1)
    x = W / 2 - total / 2
    y = card.bottom() - 48
    for i, (w_, ww) in enumerate(zip(WORDS, widths)):
        lit = (i + 0.5) / len(WORDS) <= playhead + 0.04
        if i == BAD and collapse > 0:
            draw_text(p, x, y, w_, f, MUTE)
            p.setPen(QPen(MUTE, 4))
            p.drawLine(QPointF(x - 2, y - 14),
                       QPointF(x + ww * collapse + 2, y - 14))
        else:
            draw_text(p, x, y, w_, f, TEXT if lit else DIM, alpha=1.0)
        x += ww + space


def title_block(p, t, start, cy, mark=120, size=118):
    """Logo mark + «WordMute», centred around cy."""
    a, scale = pop(t, start, 0.45)
    if a <= 0:
        return
    f = font(size, QFont.Weight.Bold)
    gap = 36
    total = mark + gap + text_width(f, "WordMute")
    p.save()
    p.setOpacity(a)
    p.translate(W / 2, cy)
    p.scale(scale, scale)
    p.translate(-W / 2, -cy)
    x = W / 2 - total / 2
    logo_mark(p, x, cy - mark / 2, mark)
    draw_text(p, x + mark + gap, cy + QFontMetricsF(f).capHeight() / 2,
              "WordMute", f, TEXT)
    p.restore()


def scene_reveal(p, t):
    title_block(p, t, T_REVEAL, 430)
    # tagline, two-tone like the site's h1
    a, dy = rise(t, 4.23)
    if a > 0:
        f = font(58, QFont.Weight.DemiBold)
        left, accent = "Нежелательные слова в видео — ", "под заглушкой"
        total = text_width(f, left) + text_width(f, accent)
        x = W / 2 - total / 2
        y = 600 + dy
        w = draw_text(p, x, y, left, f, TEXT, alpha=a)
        draw_text(p, x + w, y, accent, f, AMBER, alpha=a)
    a, dy = rise(t, 5.28)
    if a > 0:
        draw_text(p, W / 2, 690 + dy,
                  "WINDOWS · ЛОКАЛЬНАЯ ОБРАБОТКА · БЕСПЛАТНО",
                  font(22, QFont.Weight.Normal, MONO), DIM, "center", a)


def scene_queue(p, t):
    k = ease_out((t - T_QUEUE) / 0.5)
    y = 170 + (1 - k) * 260
    zoom = 1.0 + 0.05 * ease_in_out((t - 7.4) / 3.0)
    draw_pixmap_rounded(p, QUEUE, (W - QUEUE.width()) / 2, y, 14, k, zoom,
                        anchor=(W / 2, y))
    chip_row(p, ["распознаёт речь", "находит слова из вашего списка",
                 "глушит только их"], t, (T_QUEUE, 7.38, 7.91), 92)
    # the «done» toast lands bottom-right
    a = ease_out((t - T_TOAST) / 0.45)
    if a > 0:
        x = W - TOAST.width() - 90 + (1 - a) * 80
        draw_pixmap_rounded(p, TOAST, x, 800, 14, a)


def scene_review(p, t):
    k = ease_out((t - T_REVIEW) / 0.5)
    x0 = (W - REVIEW_A.width()) / 2
    x = x0 + (1 - k) * 300
    y = 190
    pm = REVIEW_B if t >= T_CLICK else REVIEW_A
    draw_pixmap_rounded(p, pm, x, y, 14, k)
    a, dy = rise(t, T_REVIEW + 0.1)
    draw_text(p, W / 2, 110 + dy,
              "Прослушать каждое слово — и вернуть одним кликом",
              font(40, QFont.Weight.DemiBold), TEXT, "center", a)
    # cursor: glides to the row-2 checkbox, clicks on the beat
    cx = x0 + META["checkbox"][0] * REVIEW_SCALE
    cy = y + META["checkbox"][1] * REVIEW_SCALE
    if t >= 11.1:
        m = ease_in_out((t - 11.1) / (T_CLICK - 11.1))
        sx, sy = x0 + 1180, y + 760
        px, py = sx + (cx - sx) * m, sy + (cy - sy) * m
        pressed = clamp((t - T_CLICK) / 0.35) if t >= T_CLICK else 0.0
        cursor(p, px, py, ease_out((t - 11.1) / 0.2), pressed)


def scene_link(p, t):
    k = ease_out((t - T_LINK) / 0.5)
    y = 300 + (1 - k) * 260
    draw_pixmap_rounded(p, ADDURL, (W - ADDURL.width()) / 2, y, 14, k)
    a, dy = rise(t, T_LINK + 0.1)
    draw_text(p, W / 2, 100 + dy,
              "Видео по ссылке: вставьте — скачает и обработает",
              font(40, QFont.Weight.DemiBold), TEXT, "center", a)
    chip_row(p, ["YouTube", "VK Видео", "RUTUBE", "Boosty"], t,
             (T_LINK, 14.22, 14.76, 15.28), 200, fill=AMBER_SOFT,
             stroke=QColor(232, 163, 61, 110), color=AMBER)


def scene_local(p, t):
    a, dy = rise(t, T_LOCAL, 0.45, 36)
    draw_text(p, W / 2, 500 + dy, "Всё на вашем компьютере.",
              font(96, QFont.Weight.Bold), TEXT, "center", a)
    a, dy = rise(t, 16.86, 0.45, 28)
    draw_text(p, W / 2, 600 + dy, "Файлы никуда не отправляются.",
              font(44, QFont.Weight.Medium), DIM, "center", a)


def scene_outro(p, t):
    title_block(p, t, T_OUTRO, 400, mark=96, size=96)
    a, dy = rise(t, 19.49)
    draw_text(p, W / 2, 580 + dy, "Скачать для Windows — бесплатно",
              font(48, QFont.Weight.DemiBold), TEXT, "center", a)
    a, dy = rise(t, 20.02)
    draw_text(p, W / 2, 660 + dy, "baudi2.github.io/wordmute",
              font(34, QFont.Weight.Normal, MONO), AMBER, "center", a)


SCENES = ((0.0, scene_hook), (T_REVEAL, scene_reveal), (T_QUEUE, scene_queue),
          (T_REVIEW, scene_review), (T_LINK, scene_link),
          (T_LOCAL, scene_local), (T_OUTRO, scene_outro))


def render_frame(t) -> QImage:
    img = QImage(W, H, QImage.Format_ARGB32)
    img.fill(BG)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    scene = SCENES[0][1]
    for start, fn in SCENES:
        if t >= start:
            scene = fn
    scene(p, t)
    # dip through the background at every cut (7 frames each side)
    dip = max((clamp(1 - abs(t - c) / 0.23) for c in CUTS), default=0.0)
    if dip > 0:
        c = QColor(BG)
        c.setAlphaF(ease_in_out(dip))
        p.fillRect(QRectF(0, 0, W, H), c)
    p.end()
    return img


def stills(times):
    out = WORK / "stills"
    out.mkdir(exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    for t in times:
        render_frame(t).save(str(out / f"t{t:05.2f}.png"))
    print("stills ->", out)


def video():
    frames = int(round(DURATION * FPS))
    target = WORK / "video_silent.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt",
           "bgra", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "slow", "-crf", "18",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(frames):
        img = render_frame(n / FPS)
        proc.stdin.write(bytes(img.constBits()))
        if n % 90 == 0:
            print(f"  frame {n}/{frames}", flush=True)
    proc.stdin.close()
    proc.wait()
    print("video ->", target, "exit", proc.returncode)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "stills"
    if mode == "stills":
        times = [float(x) for x in sys.argv[2:]] or [
            0.8, 1.75, 3.1, 3.70, 4.0, 4.7, 6.3, 6.86, 7.2, 8.3, 9.6, 10.54,
            10.9, 11.7, 12.3, 13.3, 13.70, 14.1, 15.6, 16.34, 16.7, 17.6,
            18.96, 19.3, 20.6, 21.4]
        stills(times)
    else:
        video()
