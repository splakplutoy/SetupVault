"""Regression checks for byte-exact recovery and pixel preservation."""

import unittest
from itertools import combinations

import numpy as np

from evaluation import dataset_at, demo_material
from vault import MAX_JSON_BYTES, VaultError, backup, combine, multiply, read_png, restore, split


class VaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, covers = demo_material()
        cls.covers = [read_png(cover) for cover in covers]

    def test_field_and_all_share_pairs(self):
        self.assertEqual(multiply(0x57, 0x83), 0xC1)
        data = bytes(range(256))
        shares = split(data)
        for (i, first), (j, second) in combinations(enumerate(shares, 1), 2):
            with self.subTest(pair=(i, j)):
                self.assertEqual(combine(i, first, j, second), data)

    def test_maximum_payload_and_every_pixel_delta(self):
        data = dataset_at(MAX_JSON_BYTES)
        self.assertEqual(len(data), MAX_JSON_BYTES)
        package, cards = backup(data, self.covers)
        for first, second in combinations(cards, 2):
            self.assertEqual(restore([second, first])[::2], (package, data))
        for cover, card in zip(self.covers, cards):
            delta = cover.astype(np.int16) - read_png(card).astype(np.int16)
            self.assertLessEqual(np.abs(delta).max(), 1)

    def test_rejects_invalid_json_and_undersized_cover(self):
        with self.assertRaisesRegex(VaultError, "JSON UTF-8"):
            backup(b'{"setup":NaN}', self.covers)
        with self.assertRaisesRegex(VaultError, "Sampul B"):
            backup(self.source, [self.covers[0], self.covers[1][:8, :8], self.covers[2]])

    def test_preserves_whitespace_bom_and_unicode(self):
        data = b"\xef\xbb\xbf" + '{ "catatan" : "lintasan basah — tes" }\r\n'.encode()
        _, cards = backup(data, self.covers)
        self.assertEqual(restore(cards[:2])[2], data)


if __name__ == "__main__":
    unittest.main()
