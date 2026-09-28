import unittest
from bins import bin_index

class BoundaryTests(unittest.TestCase):
    def test_half_open_boundaries(self):
        cases = [(-1, None), (0, 0), (9, 0), (10, 1), (19, 1), (20, None)]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(bin_index(value, [0, 10, 20]), expected)
    def test_negative_and_fractional_edges(self):
        self.assertEqual(bin_index(-2, [-2, -1, 0.5]), 0)
        self.assertEqual(bin_index(-1, [-2, -1, 0.5]), 1)
        self.assertEqual(bin_index(0.49, [-2, -1, 0.5]), 1)
        self.assertIsNone(bin_index(0.5, [-2, -1, 0.5]))
if __name__ == '__main__': unittest.main()
