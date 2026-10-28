import unittest

from ptl.money import to_satang, to_thb, vat_exclusive, vat_inclusive


class TestMoney(unittest.TestCase):
    def test_thb_format(self):
        self.assertEqual(to_thb(10700), "107.00")
        self.assertEqual(to_thb(5), "0.05")
        self.assertEqual(to_thb(None), "")
        self.assertEqual(to_thb(-150), "-1.50")

    def test_satang_parse(self):
        self.assertEqual(to_satang("107.00"), 10700)

    def test_vat_inclusive(self):
        self.assertEqual(vat_inclusive(10700), 700)
        self.assertEqual(vat_inclusive(10700) + 10000, 10700)

    def test_vat_exclusive(self):
        self.assertEqual(vat_exclusive(10000), 700)


if __name__ == "__main__":
    unittest.main()
