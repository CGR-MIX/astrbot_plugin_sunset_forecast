import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sunset_forecast.clients import lookup_builtin_city
from sunset_forecast.places import city_key, geocode_query_variants


class PlaceLookupTests(unittest.TestCase):
    def test_zhaoqing_variants_include_shi(self):
        variants = geocode_query_variants("肇庆")
        self.assertIn("肇庆", variants)
        self.assertIn("肇庆市", variants)

    def test_guangzhou_city_suffix_stripped(self):
        self.assertEqual(city_key("广州市"), "广州")
        self.assertEqual(city_key("肇庆市"), "肇庆")

    def test_builtin_zhaoqing_and_guangzhou(self):
        zhaoqing = lookup_builtin_city("肇庆")
        guangzhou = lookup_builtin_city("广州")
        zhaoqing_shi = lookup_builtin_city("肇庆市")
        self.assertIsNotNone(zhaoqing)
        self.assertIsNotNone(guangzhou)
        self.assertEqual(zhaoqing.admin1, "广东")
        self.assertEqual(zhaoqing_shi.name, "肇庆")
        self.assertGreater(guangzhou.population, zhaoqing.population)

    def test_unknown_builtin(self):
        self.assertIsNone(lookup_builtin_city("阿巴嘎旗"))


if __name__ == "__main__":
    unittest.main()
