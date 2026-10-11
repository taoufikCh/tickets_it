"""Aides pour l'apparence : couleurs, logo."""
import os
import re

from .config import UPLOAD_DIR


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(h):
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g_, b = (c / 255 for c in _rgb(h))
    return 0.2126 * f(r) + 0.7152 * f(g_) + 0.0722 * f(b)


def contrast_white(h):
    return 1.05 / (_lum(h) + 0.05)


def darken(h, k=0.8):
    return "#%02x%02x%02x" % tuple(int(c * k) for c in _rgb(h))


def valid_brand(h):
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", h or ""))


def logo_ext(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _remove_logo_file(name):
    if name and re.fullmatch(r"logo-[0-9a-f]{16}\.(png|jpg|gif|webp)", name):
        try:
            os.remove(os.path.join(UPLOAD_DIR, name))
        except OSError:
            pass
