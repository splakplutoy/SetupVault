"""Shamir 2-of-3 and one-bit RGB steganography for SetupVault."""

import hashlib
import io
import json
import secrets
import struct
import zlib

import numpy as np
from PIL import Image

MAX_JSON_BYTES = 65_536
MAX_PNG_BYTES = 13 * 1024 * 1024
MAX_PIXELS = 2048 * 2048
INDICES = (1, 2, 3)
MAGIC = b"SVLT"
VERSION = 1
HEADER = struct.Struct(">4sB16sBI")
CHECKSUM = struct.Struct(">I")
OVERHEAD = HEADER.size + CHECKSUM.size
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class VaultError(ValueError):
    """An input or card that cannot be processed."""


def invalid_json_constant(value):
    raise ValueError(f"Konstanta JSON tidak valid: {value}")


def validate_json(data):
    if not 1 <= len(data) <= MAX_JSON_BYTES:
        raise VaultError(f"Ukuran JSON harus 1–{MAX_JSON_BYTES:,} byte.")
    try:
        parsed = json.loads(data.decode("utf-8-sig"), parse_constant=invalid_json_constant)
    except (ValueError, RecursionError) as error:
        raise VaultError("Berkas harus berisi JSON UTF-8 yang valid.") from error
    if not isinstance(parsed, dict):
        raise VaultError("Berkas konfigurasi harus berupa objek JSON.")


def multiply(a, b):
    """Multiply two elements in GF(2^8), using x^8 + x^4 + x^3 + x + 1."""
    result = 0
    while b:
        if b & 1:
            result ^= a
        a <<= 1
        if a & 0x100:
            a ^= 0x11B
        b >>= 1
    return result


PRODUCTS = np.array(
    [[multiply(a, b) for b in range(256)] for a in range(256)], dtype=np.uint8
)
INVERSES = {a: int(np.flatnonzero(PRODUCTS[a] == 1)[0]) for a in INDICES}


def split(data):
    secret = np.frombuffer(data, dtype=np.uint8)
    slopes = np.frombuffer(secrets.token_bytes(len(data)), dtype=np.uint8)
    return [(secret ^ PRODUCTS[index, slopes]).tobytes() for index in INDICES]


def combine(first_index, first_share, second_index, second_share):
    first = np.frombuffer(first_share, dtype=np.uint8)
    second = np.frombuffer(second_share, dtype=np.uint8)
    inverse = INVERSES[first_index ^ second_index]
    slopes = PRODUCTS[inverse, first ^ second]
    return (first ^ PRODUCTS[first_index, slopes]).tobytes()


def pack_share(package_id, index, share):
    header = HEADER.pack(MAGIC, VERSION, package_id, index, len(share))
    checksum = zlib.crc32(share, zlib.crc32(header))
    return header + CHECKSUM.pack(checksum) + share


def read_png(data):
    if (
        len(data) < 33
        or len(data) > MAX_PNG_BYTES
        or data[:8] != PNG_SIGNATURE
        or data[8:16] != b"\x00\x00\x00\x0dIHDR"
    ):
        raise VaultError("Pilih berkas PNG yang valid, maksimal 13 MiB.")
    width, height = struct.unpack(">II", data[16:24])
    if not (0 < width <= 2048 and 0 < height <= 2048 and width * height <= MAX_PIXELS):
        raise VaultError("Dimensi PNG maksimal 2048 × 2048 piksel.")
    if data[24:26] != b"\x08\x02":
        raise VaultError("Gunakan PNG RGB 8-bit tanpa kanal alfa.")
    try:
        with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
            if getattr(image, "n_frames", 1) != 1 or "transparency" in image.info:
                raise VaultError("Gunakan PNG RGB tanpa animasi atau transparansi.")
            return np.array(image, dtype=np.uint8)
    except (OSError, SyntaxError, ValueError) as error:
        if isinstance(error, VaultError):
            raise
        raise VaultError("Isi PNG rusak atau tidak dapat dibaca.") from error


def encode_png(pixels):
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    return buffer.getvalue()


def embed(cover, packet):
    bits = np.unpackbits(np.frombuffer(packet, dtype=np.uint8), bitorder="big")
    if len(bits) > cover.size:
        raise VaultError("Kapasitas kartu sampul tidak cukup untuk JSON ini.")
    output = cover.copy()
    channels = output.reshape(-1)
    channels[:len(bits)] = (channels[:len(bits)] & 0xFE) | bits
    return encode_png(output)


def extract(pixels):
    channels = pixels.reshape(-1)
    if channels.size < OVERHEAD * 8:
        raise VaultError("Gambar terlalu kecil untuk memuat paket SetupVault.")

    def read_bytes(start, stop):
        return np.packbits(channels[start * 8:stop * 8] & 1, bitorder="big").tobytes()

    metadata = read_bytes(0, OVERHEAD)
    header = metadata[:HEADER.size]
    magic, version, package_id, index, length = HEADER.unpack(header)
    if magic != MAGIC:
        raise VaultError("Tidak ditemukan paket SetupVault pada gambar.")
    if version != VERSION:
        raise VaultError("Versi paket SetupVault tidak didukung.")
    if index not in INDICES or not 1 <= length <= MAX_JSON_BYTES:
        raise VaultError("Metadata kartu rusak atau tidak valid.")
    if (OVERHEAD + length) * 8 > channels.size:
        raise VaultError("Bagian cadangan terpotong.")
    share = read_bytes(OVERHEAD, OVERHEAD + length)
    stored_crc, = CHECKSUM.unpack(metadata[HEADER.size:])
    if stored_crc != zlib.crc32(share, zlib.crc32(header)):
        raise VaultError("CRC32 gagal. Metadata atau bagian cadangan berubah.")
    return package_id, index, share


def backup(data, covers):
    validate_json(data)
    if len(covers) != 3:
        raise VaultError("Pencadangan membutuhkan tiga kartu sampul.")
    for index, cover in zip(INDICES, covers):
        available = max(0, cover.size // 8 - OVERHEAD)
        if len(data) > available:
            raise VaultError(
                f"Sampul {chr(64 + index)} hanya muat {available:,} byte JSON."
            )
    package_id = secrets.token_bytes(16)
    cards = [
        embed(cover, pack_share(package_id, index, share))
        for cover, index, share in zip(covers, INDICES, split(data))
    ]
    return package_id, cards


def restore(cards):
    if len(cards) != 2:
        raise VaultError("Pemulihan membutuhkan tepat dua kartu PNG.")
    parts = []
    for number, card in enumerate(cards, 1):
        try:
            parts.append(extract(read_png(card)))
        except VaultError as error:
            raise VaultError(f"Kartu {number}: {error}") from error
    (package_id, first_index, first), (other_id, second_index, second) = parts
    if package_id != other_id:
        raise VaultError("ID paket berbeda. Pilih dua kartu dari cadangan yang sama.")
    if first_index == second_index:
        raise VaultError("Indeks kartu duplikat. Pilih dua kartu yang berbeda.")
    if len(first) != len(second):
        raise VaultError("Panjang bagian cadangan tidak cocok.")
    data = combine(first_index, first, second_index, second)
    validate_json(data)
    return package_id, [first_index, second_index], data


def digest(data):
    return hashlib.sha256(data).hexdigest()
