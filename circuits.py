"""Circuit presets and track artwork for the offline demo."""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from vault import encode_png

DEFAULT_CIRCUIT = "silverstone"
ROOT = Path(__file__).resolve().parent
FONT_PATH = ROOT / "web" / "archivo-variable.ttf"
Point = tuple[float, float]


@dataclass(frozen=True)
class Circuit:
    name: str
    length: str
    session: str
    version: int
    ambient_c: int
    start: Point
    course: tuple[Point, ...]
    pit: tuple[Point, ...]
    turn_labels: tuple[Point, ...]
    bounds: tuple[int, int, int, int]
    finish_angle: Point
    control_line: Point | None = None
    attribution: str = ""


SILVERSTONE_START = (2421, 1757)
SILVERSTONE_COURSE = (
    ((2280, 1663), (2105, 1548), (2005, 1475)),
    ((1932, 1426), (1963, 1319), (1967, 1180)),
    ((1964, 1118), (1931, 1062), (1890, 1018)),
    ((1835, 959), (1781, 905), (1743, 855)),
    ((1716, 823), (1708, 799), (1743, 783)),
    ((1790, 765), (1863, 744), (1885, 731)),
    ((1914, 716), (1915, 687), (1897, 671)),
    ((1874, 643), (1735, 617), (1656, 627)),
    ((1603, 626), (1572, 640), (1549, 672)),
    ((1412, 848), (1156, 1186), (1011, 1374)),
    ((950, 1451), (982, 1543), (1045, 1543)),
    ((1087, 1543), (1128, 1543), (1155, 1543)),
    ((1193, 1550), (1225, 1587), (1223, 1627)),
    ((1223, 1682), (1188, 1701), (1141, 1702)),
    ((1103, 1705), (1006, 1652), (926, 1619)),
    ((811, 1571), (752, 1485), (732, 1382)),
    ((709, 1234), (670, 947), (648, 791)),
    ((633, 689), (727, 635), (798, 613)),
    ((908, 579), (1031, 545), (1095, 538)),
    ((1171, 531), (1274, 520), (1344, 513)),
    ((1451, 502), (1479, 471), (1530, 441)),
    ((1575, 413), (1643, 451), (1731, 472)),
    ((1825, 493), (1845, 451), (1895, 405)),
    ((1919, 383), (1993, 374), (2020, 392)),
    ((2078, 418), (2097, 488), (2128, 525)),
    ((2161, 565), (2205, 586), (2263, 608)),
    ((2436, 682), (2911, 895), (3100, 994)),
    ((3183, 1038), (3223, 1067), (3243, 1103)),
    ((3283, 1171), (3261, 1242), (3214, 1278)),
    ((3183, 1303), (3148, 1309), (3096, 1349)),
    ((2995, 1431), (2868, 1567), (2798, 1632)),
    ((2740, 1689), (2827, 1698), (2835, 1735)),
    ((2841, 1786), (2749, 1845), (2703, 1869)),
    ((2674, 1879), (2623, 1887), (2602, 1878)),
    ((2550, 1846), (2492, 1808), SILVERSTONE_START),
)
SILVERSTONE_PIT = (
    ((3038, 1377), (2866, 1482), (2795, 1554)),
    ((2726, 1623), (2651, 1701), (2595, 1749)),
    ((2572, 1769), (2542, 1764), (2504, 1745)),
    ((2363, 1653), (2186, 1544), (2071, 1462)),
    ((2018, 1424), (2026, 1422), (2021, 1385)),
    ((2010, 1305), (2001, 1215), (1989, 1166)),
    ((1983, 1125), (1965, 1095), (1938, 1068)),
)
SILVERSTONE_TURNS = (
    (1887, 1420), (1892, 1160), (1672, 860), (1825, 697), (1608, 698),
    (1053, 1462), (1276, 1678), (700, 1522), (588, 679), (1368, 451),
    (1546, 359), (1766, 412), (1980, 315), (2219, 509), (3344, 1164),
    (2880, 1653), (2910, 1761), (2634, 1954),
)

MAP_BACKGROUND = "#202023"


def face(size, weight=650, width=100):
    font = ImageFont.truetype(str(FONT_PATH), size)
    values = {b"Weight": weight, b"Width": width}
    font.set_variation_by_axes([
        values.get(axis["name"], axis["default"]) for axis in font.get_variation_axes()
    ])
    return font


def curve(start, segments):
    points = [start]
    for first, second, end in segments:
        x0, y0 = start
        x1, y1 = first
        x2, y2 = second
        x3, y3 = end
        for step in range(1, 17):
            t = step / 16
            u = 1 - t
            points.append((
                u**3 * x0 + 3 * u**2 * t * x1 + 3 * u * t**2 * x2 + t**3 * x3,
                u**3 * y0 + 3 * u**2 * t * y1 + 3 * u * t**2 * y2 + t**3 * y3,
            ))
        start = end
    return tuple(points)


MONZA = json.loads((ROOT / "data" / "monza-f1-2026.json").read_text(encoding="utf-8"))
CIRCUITS = {
    "silverstone": Circuit(
        name="Silverstone", length="5,891", session="SIM-03", version=2, ambient_c=28,
        start=SILVERSTONE_START, course=curve(SILVERSTONE_START, SILVERSTONE_COURSE),
        pit=curve((3106, 1340), SILVERSTONE_PIT), turn_labels=SILVERSTONE_TURNS,
        bounds=(540, 280, 2895, 1715), finish_angle=(2, 3),
    ),
    "monza": Circuit(
        name="Monza", length="5,793", session="SIM-04", version=1, ambient_c=25,
        start=tuple(MONZA["start"]), course=tuple(map(tuple, MONZA["course"])),
        pit=tuple(map(tuple, MONZA["pit"])), turn_labels=tuple(map(tuple, MONZA["turn_labels"])),
        bounds=tuple(MONZA["bounds"]), finish_angle=(0.3, 3),
        control_line=tuple(MONZA["control_line"]), attribution=MONZA["attribution"],
    ),
}


def render_track(circuit, size, *, numbered):
    width, height = (2 * dimension for dimension in size)
    image = Image.new("RGB", (width, height), MAP_BACKGROUND)
    draw = ImageDraw.Draw(image)
    left, top, map_width, map_height = circuit.bounds
    scale = min((width - 24) / map_width, (height - 20) / map_height)
    offset_x = (width - map_width * scale) / 2 - left * scale
    offset_y = (height - map_height * scale) / 2 - top * scale

    def transform(point):
        return (point[0] * scale + offset_x, point[1] * scale + offset_y)

    draw.line(
        [transform(point) for point in circuit.pit],
        fill="#9696a0", width=8 if numbered else 4, joint="curve",
    )
    draw.line(
        [transform(point) for point in circuit.course],
        fill="#f5f5f7", width=16 if numbered else 10, joint="curve",
    )
    mark = 8.5 if numbered else 5
    offset_x_mark, offset_y_mark = (axis * mark for axis in circuit.finish_angle)

    def draw_marker(point, color):
        x, y = transform(point)
        draw.line(
            [(x - offset_x_mark, y + offset_y_mark), (x + offset_x_mark, y - offset_y_mark)],
            fill=color, width=10 if numbered else 6,
        )

    draw_marker(circuit.start, "#ff5148")
    if numbered:
        if circuit.control_line is not None:
            draw_marker(circuit.control_line, "#ffc66d")
        label_font = face(53, 750)
        for index, position in enumerate(circuit.turn_labels, start=1):
            draw.text(
                transform(position), str(index), anchor="mm", font=label_font,
                fill="#f5f5f7", stroke_width=4, stroke_fill=MAP_BACKGROUND,
            )
        if circuit.attribution:
            draw.text((width - 22, height - 14), circuit.attribution,
                      font=face(25, 550), fill="#c2c2c9", anchor="rs")
    return image.resize(size, Image.Resampling.LANCZOS)


@lru_cache(maxsize=len(CIRCUITS))
def detail_png(circuit_id=DEFAULT_CIRCUIT):
    return encode_png(np.asarray(render_track(CIRCUITS[circuit_id], (1200, 720), numbered=True)))


def session_card(circuit, letter, holder):
    image = Image.new("RGB", (512, 512), "#18181b")
    draw = ImageDraw.Draw(image)
    draw.polygon(((0, 0), (266, 0), (252, 9), (0, 9)), fill="#e10600")
    draw.text((27, 32), "SetupVault", font=face(23, 800), fill="#f5f5f7")
    draw.text((485, 35), f"{circuit.session} / SETUP {circuit.version:02}", anchor="rt", font=face(15, 650), fill="#c2c2c9")
    draw.text((25, 72), circuit.name, font=face(52, 870, 114), fill="#f5f5f7")
    draw.text((28, 135), "Grand Prix Circuit", font=face(18, 550), fill="#c2c2c9")
    image.paste(render_track(circuit, (456, 242), numbered=False), (28, 169))
    start_label = "Start / finish" if circuit.control_line is None else "Start"
    for x, label, color in ((40, start_label, "#ff5148"), (166, "Pit lane", "#9696a0")):
        draw.line(((x, 392), (x + 16, 392)), fill=color, width=3)
        draw.text((x + 23, 392), label, anchor="lm", font=face(12, 575), fill="#e5e5e9")
    if circuit.attribution:
        draw.text((484, 422), circuit.attribution, font=face(10, 575), fill="#c2c2c9", anchor="rs")
    draw.line(((28, 427), (484, 427)), fill="#4f4f58", width=1)
    draw.rectangle((28, 447, 69, 487), fill="#e10600")
    draw.text((49, 467), letter, anchor="mm", font=face(23, 800), fill="#ffffff")
    draw.text((82, 455), holder, anchor="lt", font=face(22, 750), fill="#f5f5f7")
    draw.text((82, 481), "Setup sintetis", anchor="lm", font=face(13, 500), fill="#c2c2c9")
    draw.text((484, 463), f"Kering / {circuit.ambient_c} °C", anchor="rm", font=face(17, 625), fill="#e5e5e9")
    return encode_png(np.asarray(image))
