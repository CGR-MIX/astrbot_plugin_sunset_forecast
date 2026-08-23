import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sunset_forecast.report import (
    CloudSeaDay,
    DayForecast,
    format_cloudsea_chat,
    format_markdown,
    format_sunset_chat,
    format_text,
)


def fake_day() -> DayForecast:
    return DayForecast(
        day_offset=0,
        local_date="2026-08-23",
        location_input="上海",
        place={
            "name": "上海",
            "admin1": "上海市",
            "country": "中国",
            "latitude": 31.222,
            "longitude": 121.458,
            "timezone": "Asia/Shanghai",
        },
        sunset_local="2026-08-23 18:28:00",
        sunrise_local="2026-08-23 05:24:00",
        sunsetbot={
            "gfs": {
                "status": "ok",
                "quality_text": "0.005（微烧）",
                "aod_text": "0.153（水晶）",
                "times_name": "中午时次",
            },
            "ec": {
                "status": "ok",
                "quality_text": "0.0（不烧）",
                "aod_text": "0.151（水晶）",
                "times_name": "凌晨时次",
            },
            "blended_vividness": 0.003,
            "blended_grade": "微烧",
        },
        engine={
            "score_0_100": 35.9,
            "grade": "小烧",
            "p_visible": 0.18,
            "p_worth_going": 0.06,
            "advice": "今晚大概率不烧",
            "factors": [
                {
                    "key": "precip",
                    "name": "降水",
                    "weight": 0.1,
                    "value": 0.0,
                    "detail": "降水概率 60%",
                }
            ],
        },
        combined={
            "p_visible": 0.18,
            "p_worth_going": 0.06,
            "confidence": 0.61,
            "advice": "今晚大概率不烧",
        },
    )


class ReportTests(unittest.TestCase):
    def test_markdown_contains_core_fields(self):
        markdown = format_markdown([fake_day()])
        self.assertIn("晚霞预报 · 上海市 上海", markdown)
        self.assertIn("0.005（微烧）", markdown)
        self.assertIn("18%", markdown)
        self.assertIn("今晚大概率不烧", markdown)
        self.assertIn("五因子拆解", markdown)

    def test_text_contains_sunset_time(self):
        text = format_text([fake_day()])
        self.assertIn("18:28", text)
        self.assertIn("SunsetBot GFS", text)

    def test_sunset_chat_is_short(self):
        chat = format_sunset_chat([fake_day()])
        self.assertIn("上海晚霞", chat)
        self.assertIn("18%", chat)
        self.assertNotIn("████", chat)

    def test_cloudsea_chat_mentions_probability(self):
        day = CloudSeaDay(
            day_offset=1,
            local_date="2026-08-24",
            location_input="新兴风车山",
            spot_name="新兴风车山",
            note="",
            place={"name": "新兴风车山", "admin1": "广东", "latitude": 22.7289, "longitude": 112.0587},
            peak_m=1137.0,
            valley_m=80.0,
            sunrise_local="2026-08-24 06:11:00",
            sample_time="2026-08-24T05:00",
            p_appear=0.30,
            grade="有机会",
            advice="机会一般，不专程跑也行",
            score_0_100=30.2,
            factors=[],
            diagnostics={"rh_valley": 93.0, "rh_peak": 87.0},
        )
        chat = format_cloudsea_chat([day])
        self.assertIn("30%", chat)
        self.assertIn("1137", chat)


if __name__ == "__main__":
    unittest.main()
