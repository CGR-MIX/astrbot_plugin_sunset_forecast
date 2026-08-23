import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sunset_forecast.cloudsea import (
    CloudSeaSample,
    PressureLevel,
    estimate_cloud_base_m,
    field_at_height,
    pick_best_morning,
    score_cloud_sea_sample,
)
from sunset_forecast.spots import resolve_spot


def classic_levels() -> tuple[PressureLevel, ...]:
    return (
        PressureLevel(1000, 20, 22.0, 70.0, 10.0, 2.0),
        PressureLevel(975, 240, 21.0, 92.0, 55.0, 2.0),
        PressureLevel(950, 470, 20.0, 94.0, 60.0, 2.2),
        PressureLevel(925, 700, 19.0, 90.0, 40.0, 2.5),
        PressureLevel(900, 940, 18.5, 62.0, 8.0, 3.5),
        PressureLevel(850, 1450, 16.0, 48.0, 6.0, 4.0),
        PressureLevel(800, 1960, 12.0, 35.0, 5.0, 5.0),
    )


def soup_levels() -> tuple[PressureLevel, ...]:
    return (
        PressureLevel(1000, 15, 27.0, 96.0, 40.0, 4.0),
        PressureLevel(975, 236, 26.0, 95.0, 38.0, 4.0),
        PressureLevel(950, 463, 25.0, 94.0, 37.0, 4.0),
        PressureLevel(925, 698, 23.0, 98.0, 66.0, 4.0),
        PressureLevel(900, 938, 22.0, 98.0, 68.0, 4.0),
        PressureLevel(850, 1436, 20.0, 89.0, 31.0, 5.0),
        PressureLevel(800, 1959, 18.0, 89.0, 35.0, 6.0),
    )


def sample_from(levels: tuple[PressureLevel, ...], **overrides) -> CloudSeaSample:
    base = dict(
        time="2026-08-24T06:00",
        temperature_2m=20.0,
        dew_point_2m=16.0,
        humidity_2m=72.0,
        cloud_low=55.0,
        cloud_mid=10.0,
        cloud_high=5.0,
        cloud_total=50.0,
        visibility_m=8000.0,
        precip_mm=0.0,
        precip_probability=5.0,
        wind_10m_ms=2.0,
        levels=levels,
    )
    base.update(overrides)
    return CloudSeaSample(**base)


class SpotTests(unittest.TestCase):
    def test_xinxing_aliases(self):
        for name in ("新兴风车山", "风车山", "18号风车", "水源山"):
            spot = resolve_spot(name)
            self.assertIsNotNone(spot)
            self.assertEqual(spot.peak_m, 1137.0)
            self.assertAlmostEqual(spot.latitude, 22.7289)

    def test_unknown_spot(self):
        self.assertIsNone(resolve_spot("上海"))


class CloudSeaScoringTests(unittest.TestCase):
    def test_height_interpolation(self):
        rh = field_at_height(classic_levels(), 1137.0, "rh")
        self.assertIsNotNone(rh)
        self.assertGreater(rh, 48.0)
        self.assertLess(rh, 62.0)

    def test_cloud_base_skips_dry_surface(self):
        base = estimate_cloud_base_m(classic_levels(), humidity_2m=72.0, valley_m=80.0)
        self.assertGreaterEqual(base, 200.0)
        self.assertLess(base, 500.0)

    def test_classic_setup_beats_in_cloud(self):
        good = score_cloud_sea_sample(
            sample_from(classic_levels()),
            peak_m=1137.0,
            valley_m=80.0,
        )
        bad = score_cloud_sea_sample(
            sample_from(
                soup_levels(),
                humidity_2m=93.0,
                cloud_low=0.0,
                cloud_total=100.0,
                precip_mm=0.1,
                precip_probability=60.0,
                visibility_m=8100.0,
            ),
            peak_m=1137.0,
            valley_m=80.0,
        )
        self.assertGreater(good.p_appear, 0.45)
        self.assertIn(good.grade, {"较明显", "成海机会高", "条件很好"})
        self.assertLess(bad.p_appear, 0.22)
        self.assertGreater(good.p_appear, bad.p_appear)

    def test_peak_in_cloud_caps_probability(self):
        result = score_cloud_sea_sample(
            sample_from(soup_levels(), humidity_2m=96.0),
            peak_m=1137.0,
            valley_m=80.0,
        )
        self.assertLessEqual(result.p_appear, 0.18)
        self.assertIn("云里", result.advice)

    def test_picks_better_morning_hour(self):
        samples = [
            sample_from(soup_levels(), time="2026-08-24T05:00", humidity_2m=96.0),
            sample_from(classic_levels(), time="2026-08-24T06:00"),
            sample_from(soup_levels(), time="2026-08-24T07:00", humidity_2m=96.0),
        ]
        best = pick_best_morning(samples, 1, peak_m=1137.0, valley_m=80.0)
        self.assertEqual(best.sample_time, "2026-08-24T06:00")
        self.assertGreater(best.p_appear, 0.4)


if __name__ == "__main__":
    unittest.main()
