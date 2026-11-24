"""Synthetic session cards and the reproducible SetupVault evaluation protocol."""

import argparse
import io
import json
import math
import random
import string
from functools import lru_cache
from itertools import combinations
from statistics import mean
from time import perf_counter

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

from circuits import CIRCUITS, DEFAULT_CIRCUIT, session_card
from vault import OVERHEAD, VaultError, backup, encode_png, read_png, restore

SIZES = (100, 500, 1024, 2048, 4096, 8192, 16_384, 32_768, 49_152, 65_536)
PAIRS = tuple(combinations(range(3), 2))
REPEATS = 5
SETUPS = {
    "silverstone": {
        "front_ride_height_mm": 33,
        "rear_ride_height_mm": 56,
        "front_spring_n_per_mm": 140,
        "rear_spring_n_per_mm": 125,
        "brake_bias_front_pct": 56.5,
        "tire_pressure_kpa": {"front": 180, "rear": 175},
    },
    "monza": {
        "front_ride_height_mm": 31,
        "rear_ride_height_mm": 50,
        "front_spring_n_per_mm": 135,
        "rear_spring_n_per_mm": 120,
        "brake_bias_front_pct": 57.5,
        "tire_pressure_kpa": {"front": 178, "rear": 174},
    },
}


@lru_cache(maxsize=len(CIRCUITS))
def demo_material(circuit_id=DEFAULT_CIRCUIT):
    circuit = CIRCUITS[circuit_id]
    config = {
        "session": circuit.session,
        "version": circuit.version,
        "vehicle": "SV-17",
        "circuit": circuit.name,
        "conditions": {"track": "kering", "ambient_c": circuit.ambient_c},
        "setup": SETUPS[circuit_id],
    }
    data = (json.dumps(config, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    covers = tuple(
        session_card(circuit, *spec)
        for spec in [("A", "Engineer"), ("B", "Kru"), ("C", "Arsip")]
    )
    return data, covers


def dataset_at(size):
    prefix = b'{"session":"SIM-03","version":2,"synthetic":true,"notes":"'
    suffix = b'"}'
    count = size - len(prefix) - len(suffix)
    notes = "".join(random.Random(size).choices(string.ascii_letters + string.digits, k=count))
    return prefix + notes.encode("ascii") + suffix


def blur(pixels):
    return gaussian_filter(pixels, sigma=1.5, radius=5, axes=(0, 1))


def image_metrics(original, changed):
    mse = float(np.mean(np.square(original - changed)))
    psnr = 10 * math.log10(255**2 / mse) if mse else None
    first_mean, second_mean = blur(original), blur(changed)
    first_var = blur(original**2) - first_mean**2
    second_var = blur(changed**2) - second_mean**2
    covariance = blur(original * changed) - first_mean * second_mean
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    ssim_map = (
        (2 * first_mean * second_mean + c1) * (2 * covariance + c2)
        / ((first_mean**2 + second_mean**2 + c1) * (first_var + second_var + c2))
    )
    return mse, psnr, float(ssim_map[5:-5, 5:-5].mean())


def rejection_cases(source, covers, cards):
    _, other_cards = backup(source, covers)
    altered = read_png(cards[0])
    altered.reshape(-1)[OVERHEAD * 8] ^= 1

    jpeg = io.BytesIO()
    Image.fromarray(read_png(cards[0])).save(jpeg, format="JPEG", quality=85)
    jpeg.seek(0)
    with Image.open(jpeg) as compressed:
        reencoded = encode_png(np.asarray(compressed.convert("RGB")))

    scenarios = [
        ("Satu kartu", cards[:1], "tepat dua kartu"),
        ("Kartu duplikat A + A", [cards[0], cards[0]], "Indeks kartu duplikat"),
        ("Kartu dari paket berbeda", [cards[0], other_cards[1]], "ID paket berbeda"),
        ("Satu bit bagian berubah", [encode_png(altered), cards[1]], "CRC32 gagal"),
        ("PNG ke JPEG kualitas 85 lalu ke PNG", [reencoded, cards[1]], None),
    ]
    results = []
    for label, pair, expected in scenarios:
        try:
            _, _, data = restore(pair)
            detail = "JSON identik." if data == source else "JSON berbeda dari sumber."
            passed = False if expected else None
        except VaultError as error:
            detail = str(error)
            passed = expected in detail if expected else None
        results.append({"label": label, "pass": passed, "detail": detail})
    return results


def evaluate(circuit_id=DEFAULT_CIRCUIT):
    demo, sample_covers = demo_material(circuit_id)
    covers = [read_png(cover) for cover in sample_covers]
    originals = [cover.astype(np.float64) for cover in covers]
    rows = []
    for size in SIZES:
        source = dataset_at(size)
        backup_ms, restore_ms, png_bytes, quality = [], [], [], []
        successes = 0
        for _ in range(REPEATS):
            started = perf_counter()
            _, cards = backup(source, covers)
            backup_ms.append((perf_counter() - started) * 1000)
            png_bytes.append(sum(len(card) for card in cards))

            for first, second in PAIRS:
                started = perf_counter()
                try:
                    _, _, recovered = restore([cards[first], cards[second]])
                    successes += recovered == source
                except VaultError:
                    pass
                restore_ms.append((perf_counter() - started) * 1000)

            for original, card in zip(originals, cards):
                quality.append(image_metrics(original, read_png(card).astype(np.float64)))

        mse, psnr, ssim = zip(*quality)
        rows.append({
            "bytes": size,
            "successes": successes,
            "attempts": len(restore_ms),
            "backup_ms": mean(backup_ms),
            "restore_ms": mean(restore_ms),
            "mse": mean(mse),
            "psnr_db": mean(p for p in psnr if p is not None) if any(p is not None for p in psnr) else None,
            "ssim": mean(ssim),
            "packet_bytes": 3 * (size + OVERHEAD),
            "png_bytes": mean(png_bytes),
        })
    _, demo_cards = backup(demo, covers)
    return {
        "rows": rows,
        "scenarios": rejection_cases(demo, covers, demo_cards),
        "repeats": REPEATS,
        "image_comparisons": len(SIZES) * REPEATS * len(covers),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluasi sampul sirkuit SetupVault.")
    parser.add_argument("--circuit", choices=CIRCUITS, default=DEFAULT_CIRCUIT)
    print(json.dumps(evaluate(parser.parse_args().circuit), ensure_ascii=True, indent=2))
