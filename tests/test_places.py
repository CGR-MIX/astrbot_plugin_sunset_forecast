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

    def test_builtin_covers_prefecture_and_county(self):
        cases = {
            "广州": "广东",
            "肇庆": "广东",
            "肇庆市": "广东",
            "广东肇庆": "广东",
            "拉萨": "西藏",
            "喀什": "新疆",
            "西双版纳": "云南",
            "恩施": "湖北",
            "锡林浩特": "内蒙古",
            "义乌": "浙江",
            "昆山": "江苏",
            "香港": "香港",
            "台北": "台湾",
        }
        for name, admin1 in cases.items():
            place = lookup_builtin_city(name)
            self.assertIsNotNone(place, name)
            self.assertEqual(place.admin1, admin1, name)
            self.assertTrue(15 < place.latitude < 55, name)
            self.assertTrue(73 < place.longitude < 136, name)

    def test_unknown_builtin(self):
        self.assertIsNone(lookup_builtin_city("阿巴嘎旗某某不存在"))


if __name__ == "__main__":
    unittest.main()
