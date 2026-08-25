import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sunset_forecast.clients import _city_candidates, geocode, lookup_builtin_city
from sunset_forecast.places import (
    DEFAULT_SUNSET_LOCATION,
    DUANZHOU_LAT,
    DUANZHOU_LNG,
    city_key,
    geocode_query_variants,
    lookup_china_city,
    sunsetbot_query_city,
)


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
        self.assertIsNone(lookup_builtin_city("火星基地xyz123"))

    def test_zhaoqing_works_without_county_json(self):
        from sunset_forecast import places

        places._CITIES = None
        try:
            original = places._read_city_json
            places._read_city_json = lambda: {}
            places._CITIES = None
            place = lookup_builtin_city("肇庆")
            self.assertIsNotNone(place)
            self.assertEqual(place.admin1, "广东")
        finally:
            places._read_city_json = original
            places._CITIES = None

    def test_zhaoqing_from_messy_chat_text(self):
        samples = [
            "/晚霞 肇庆",
            "晚霞 肇庆",
            "[CQ:at,qq=123456] /晚霞 肇庆",
            "@机器人 晚霞 肇庆",
            "查一下肇庆",
        ]
        for text in samples:
            hit = lookup_china_city(text)
            self.assertIsNotNone(hit, text)
            self.assertEqual(hit[2], "广东", text)
            self.assertEqual(hit[3], "肇庆", text)
            place = geocode(text)
            self.assertEqual(place.admin1, "广东", text)

    def test_duanzhou_aliases_resolve_to_zhaoqing_district(self):
        samples = (
            DEFAULT_SUNSET_LOCATION,
            "端州区",
            "端州",
            "肇庆端州",
            "广东肇庆端州区",
        )
        for name in samples:
            hit = lookup_china_city(name)
            self.assertIsNotNone(hit, name)
            lat, lng, admin1, display = hit
            self.assertEqual(admin1, "广东", name)
            self.assertEqual(display, "端州区", name)
            self.assertAlmostEqual(lat, DUANZHOU_LAT, places=4, msg=name)
            self.assertAlmostEqual(lng, DUANZHOU_LNG, places=4, msg=name)
            self.assertEqual(sunsetbot_query_city(name), "肇庆", name)
            candidates = _city_candidates(name)
            self.assertEqual(candidates[0], "肇庆", name)
            self.assertIn("广东-肇庆", candidates)
            self.assertNotIn("端州", candidates)

    def test_duanzhou_works_without_county_json(self):
        from sunset_forecast import places

        places._CITIES = None
        try:
            original = places._read_city_json
            places._read_city_json = lambda: {}
            places._CITIES = None
            hit = lookup_china_city(DEFAULT_SUNSET_LOCATION)
            self.assertIsNotNone(hit)
            self.assertEqual(hit[2], "广东")
            self.assertEqual(hit[3], "端州区")
        finally:
            places._read_city_json = original
            places._CITIES = None

    def test_config_default_is_duanzhou(self):
        import json

        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        self.assertEqual(config["location"], DEFAULT_SUNSET_LOCATION)
        self.assertEqual(schema["default_city"]["default"], DEFAULT_SUNSET_LOCATION)


if __name__ == "__main__":
    unittest.main()
