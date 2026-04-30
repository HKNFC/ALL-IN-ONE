"""
Uygulama ikonu oluşturur — pillow gerektirmez, saf Python ile SVG→PNG→ICNS
"""
import os
import sys
import struct
import zlib
import subprocess


def create_png_bytes(size=512):
    """Borsa grafik temalı basit bir PNG ikonu oluşturur (saf Python, pillow yok)."""
    width = height = size

    def make_pixel(r, g, b, a=255):
        return bytes([r, g, b, a])

    # Tuval: koyu arka plan
    bg = make_pixel(14, 17, 23)
    pixels = [bg] * (width * height)

    def set_px(x, y, color):
        if 0 <= x < width and 0 <= y < height:
            pixels[y * width + x] = color

    def fill_rect(x0, y0, x1, y1, color):
        for y in range(y0, y1):
            for x in range(x0, x1):
                set_px(x, y, color)

    def draw_line(x0, y0, x1, y1, color, thick=3):
        dx = abs(x1 - x0); dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            for tx in range(-thick//2, thick//2+1):
                for ty in range(-thick//2, thick//2+1):
                    set_px(x0+tx, y0+ty, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy; x0 += sx
            if e2 < dx:
                err += dx; y0 += sy

    s = size
    green = make_pixel(0, 204, 150)
    red   = make_pixel(239, 85, 59)
    white = make_pixel(220, 220, 220)
    gray  = make_pixel(80, 80, 100)

    # Çerçeve
    fill_rect(0, 0, s, s, make_pixel(14, 17, 23))
    fill_rect(int(s*.03), int(s*.03), int(s*.97), int(s*.97), make_pixel(22, 26, 36))

    # Grid çizgileri
    for i in range(1, 5):
        y = int(s * 0.15 + i * s * 0.14)
        for x in range(int(s*.08), int(s*.92)):
            set_px(x, y, make_pixel(30, 35, 50))

    # Kandil grafiği (basit OHLC barları)
    candles = [
        (0.15, 0.80, 0.60, 0.72, False),
        (0.25, 0.75, 0.50, 0.65, True),
        (0.35, 0.65, 0.42, 0.55, True),
        (0.45, 0.70, 0.48, 0.58, False),
        (0.55, 0.55, 0.30, 0.45, True),
        (0.65, 0.45, 0.25, 0.35, True),
        (0.75, 0.50, 0.28, 0.40, False),
        (0.85, 0.38, 0.18, 0.28, True),
    ]

    for (cx_r, high_r, low_r, open_r, is_green) in candles:
        cx   = int(s * cx_r)
        high = int(s * high_r)
        low  = int(s * low_r)
        op   = int(s * open_r)
        cl   = int(s * (open_r - 0.08 if is_green else open_r + 0.08))
        color = green if is_green else red
        bw = max(6, int(s * 0.045))
        # Fitil
        for y in range(min(high, low), max(high, low)):
            set_px(cx, y, color)
        # Gövde
        fill_rect(cx - bw//2, min(op, cl), cx + bw//2, max(op, cl), color)

    # Trend çizgisi
    pts = [(0.10, 0.85), (0.25, 0.78), (0.40, 0.62), (0.55, 0.50), (0.70, 0.38), (0.90, 0.22)]
    for i in range(len(pts)-1):
        x0, y0 = int(pts[i][0]*s), int(pts[i][1]*s)
        x1, y1 = int(pts[i+1][0]*s), int(pts[i+1][1]*s)
        draw_line(x0, y0, x1, y1, green, thick=max(3, s//100))

    # Raw RGBA → PNG
    raw = b""
    for y in range(height):
        raw += b"\x00"  # filter type none
        for x in range(width):
            raw += pixels[y * width + x]

    def make_chunk(chunk_type, data):
        c = chunk_type + data
        crc = zlib.crc32(c) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    compressed = zlib.compress(raw, 9)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + make_chunk(b"IHDR", ihdr_data)
        + make_chunk(b"IDAT", compressed)
        + make_chunk(b"IEND", b"")
    )
    return png


def build_icns(sizes=(16, 32, 64, 128, 256, 512)):
    """macOS .icns dosyası oluşturur."""
    icns_types = {
        16:  b"icp4", 32:  b"icp5", 64:  b"icp6",
        128: b"ic07", 256: b"ic08", 512: b"ic09",
    }
    chunks = b""
    for size in sizes:
        png_data = create_png_bytes(size)
        type_tag = icns_types.get(size, b"ic08")
        chunk_size = 8 + len(png_data)
        chunks += type_tag + struct.pack(">I", chunk_size) + png_data

    total_size = 8 + len(chunks)
    return b"icns" + struct.pack(">I", total_size) + chunks


def build_ico(sizes=(16, 32, 48, 64, 128, 256)):
    """Windows .ico dosyası oluşturur (PNG embed)."""
    images = [(s, create_png_bytes(s)) for s in sizes]
    n = len(images)
    header = struct.pack("<HHH", 0, 1, n)
    offset = 6 + n * 16
    directory = b""
    for size, png_data in images:
        sz = size if size < 256 else 0
        directory += struct.pack("<BBBBHHII", sz, sz, 0, 0, 1, 32, len(png_data), offset)
        offset += len(png_data)
    image_data = b"".join(png for _, png in images)
    return header + directory + image_data


if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))

    icns_path = os.path.join(base, "icon.icns")
    ico_path  = os.path.join(base, "icon.ico")
    png_path  = os.path.join(base, "icon.png")

    print("İkon oluşturuluyor...")

    with open(icns_path, "wb") as f:
        f.write(build_icns())
    print(f"  macOS: {icns_path} ({os.path.getsize(icns_path)//1024} KB)")

    with open(ico_path, "wb") as f:
        f.write(build_ico())
    print(f"  Windows: {ico_path} ({os.path.getsize(ico_path)//1024} KB)")

    with open(png_path, "wb") as f:
        f.write(create_png_bytes(512))
    print(f"  PNG: {png_path} ({os.path.getsize(png_path)//1024} KB)")

    print("İkon oluşturma tamamlandı ✓")
