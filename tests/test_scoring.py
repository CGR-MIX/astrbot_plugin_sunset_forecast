import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sunset_forecast.scoring import (
    HourSample,
    advice_from_probs,
    aod_grade,
    blend_vividness,
    combine_probabilities,
    engine_probabilities,
    parse_labeled_number,
    score_clear_horizon,
    score_cloud_layers,
    score_high_canvas,
    score_hour_samples,
    score_precip,
    sunsetbot_probabilities,
    vividness_grade,
)


def sample(**overrides) -> HourSample:
    base = dict(
        time="2026-08-23T18:00",
        cloud_low=10,
        cloud_mid=20,
        cloud_high=50,
        cloud_total=45,
        visibility_m=20000,
        humidity=55,
        precip_probability=5,
        precipitation_mm=0.0,
        aod=0.15,
    )
    base.update(overrides)
    return HourSample(**base)


class ScoringTests(unittest.TestCase):
    def test_parse_labeled_number(self):
        value, label = parse_labeled_number("0.163（小烧）")
        self.assertAlmostEqual(value, 0.163)
        self.assertEqual(label, "小烧")
        value, label = parse_labeled_number("0.0（不烧）")
        self.assertEqual(value, 0.0)
        self.assertEqual(label, "不烧")
        value, label = parse_labeled_number("")
        self.assertIsNone(value)
        self.assertIsNone(label)

    def test_vividness_and_aod_bands(self):
        self.assertEqual(vividness_grade(0.0), "不烧")
        self.assertEqual(vividness_grade(0.005), "微烧")
        self.assertEqual(vividness_grade(0.163), "小烧")
        self.assertEqual(vividness_grade(0.5), "中烧")
        self.assertEqual(vividness_grade(1.2), "典型大烧")
        self.assertEqual(aod_grade(0.153), "水晶")
        self.assertEqual(aod_grade(0.741), "大污")
        self.assertEqual(aod_grade(0.893), "非常污")

    def test_high_clouds_beat_clear_sky(self):
        high, _ = score_cloud_layers(5, 10, 55)
        clear, _ = score_cloud_layers(5, 0, 0)
        self.assertGreater(high, clear)

    def test_low_clouds_block_horizon(self):
        self.assertGreater(score_clear_horizon(8), score_clear_horizon(50))
        open_sky, _ = score_cloud_layers(8, 15, 50)
        blocked, _ = score_cloud_layers(80, 15, 50)
        self.assertGreater(open_sky, blocked)

    def test_rain_crushes_score(self):
        dry, _ = score_precip(5, 0.0)
        wet, _ = score_precip(80, 1.2)
        self.assertGreater(dry, 0.8)
        self.assertLess(wet, 0.2)

    def test_good_setup_outperforms_drizzle_no_canvas(self):
        good = score_hour_samples(
            [
                sample(time="2026-08-23T17:00", cloud_low=8, cloud_high=40),
                sample(time="2026-08-23T18:00", cloud_low=10, cloud_high=55, cloud_mid=18),
                sample(time="2026-08-23T19:00", cloud_low=12, cloud_high=60),
            ],
            1,
        )
        bad = score_hour_samples(
            [
                sample(
                    time="2026-08-23T17:00",
                    cloud_low=23,
                    cloud_mid=6,
                    cloud_high=0,
                    cloud_total=24,
                    visibility_m=8160,
                    humidity=77,
                    precip_probability=86,
                    precipitation_mm=0.0,
                ),
                sample(
                    time="2026-08-23T18:00",
                    cloud_low=23,
                    cloud_mid=2,
                    cloud_high=0,
                    cloud_total=23,
                    visibility_m=11160,
                    humidity=81,
                    precip_probability=60,
                    precipitation_mm=0.1,
                ),
                sample(
                    time="2026-08-23T19:00",
                    cloud_low=20,
                    cloud_mid=1,
                    cloud_high=0,
                    cloud_total=20,
                    visibility_m=11440,
                    humidity=84,
                    precip_probability=26,
                    precipitation_mm=0.0,
                ),
            ],
            1,
        )
        self.assertGreater(good.score_0_100, 55)
        self.assertLess(bad.score_0_100, 42)
        self.assertEqual(bad.grade, "小烧")
        self.assertGreater(good.p_visible, bad.p_visible)

    def test_probabilities_are_monotonic_and_bounded(self):
        low = engine_probabilities(10, 0.01)
        high = engine_probabilities(80, 1.1)
        self.assertLess(low[0], high[0])
        self.assertLess(low[1], high[1])
        for value in (*low, *high, *sunsetbot_probabilities(0.0), *sunsetbot_probabilities(1.2)):
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_zero_vividness_keeps_visible_probability_low(self):
        p_visible, p_worth = sunsetbot_probabilities(0.0)
        self.assertLessEqual(p_visible, 0.12)
        self.assertLessEqual(p_worth, 0.04)

    def test_blend_prefers_gfs(self):
        blended = blend_vividness(1.0, 0.0)
        self.assertGreater(blended, 0.5)
        self.assertEqual(blend_vividness(None, 0.2), 0.2)
        self.assertIsNone(blend_vividness(None, None))

    def test_combine_uses_sunsetbot_when_present(self):
        engine = score_hour_samples(
            [sample(time="17:00"), sample(time="18:00"), sample(time="19:00")],
            1,
        )
        p_visible, p_worth, confidence = combine_probabilities(engine, 0.01)
        self.assertLess(p_visible, engine.p_visible)
        self.assertGreaterEqual(confidence, 0.35)
        self.assertIn("不烧", advice_from_probs(0.1, 0.02, 0.0))
        self.assertIn("出门", advice_from_probs(0.6, 0.5, 0.5))

    def test_high_canvas_score_peaks_in_mid_range(self):
        self.assertGreater(score_high_canvas(50), score_high_canvas(0))
        self.assertGreater(score_high_canvas(50), score_high_canvas(100))


if __name__ == "__main__":
    unittest.main()
