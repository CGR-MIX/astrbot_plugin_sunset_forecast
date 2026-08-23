"""晚霞质量评分与概率估计。

评分刻度对齐 SunsetBot 公开说明（鲜艳度 / AOD），因子权重参考
Henriksson 2019、多层云量经验规则，以及 Open-Meteo 可免费拿到的小时要素。

SunsetBot 官方鲜艳度本身不是概率；本模块把鲜艳度和五因子得分
分别映射成「能看见晚霞」「值得出门」两个概率，并标明为模型估计。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

VIVIDNESS_BANDS: tuple[tuple[float, float, str], ...] = (
    (0.0, 0.001, "不烧"),
    (0.001, 0.05, "微烧"),
    (0.05, 0.2, "小烧"),
    (0.2, 0.4, "小到中烧"),
    (0.4, 0.6, "中烧"),
    (0.6, 0.8, "中到大烧"),
    (0.8, 1.0, "大烧（有瑕疵）"),
    (1.0, 1.5, "典型大烧"),
    (1.5, 2.0, "优质大烧"),
    (2.0, float("inf"), "世纪大烧"),
)

# 五因子 0–100 分到中文等级。不要把四五十分说成大烧。
ENGINE_GRADE_BANDS: tuple[tuple[float, float, str], ...] = (
    (0.0, 20.0, "不烧"),
    (20.0, 35.0, "微烧"),
    (35.0, 50.0, "小烧"),
    (50.0, 63.0, "小到中烧"),
    (63.0, 74.0, "中烧"),
    (74.0, 83.0, "中到大烧"),
    (83.0, 90.0, "大烧（有瑕疵）"),
    (90.0, 96.0, "典型大烧"),
    (96.0, 101.0, "优质大烧"),
)

AOD_BANDS: tuple[tuple[float, float, str], ...] = (
    (0.0, 0.1, "高级水晶"),
    (0.1, 0.2, "水晶"),
    (0.2, 0.3, "偏蓝"),
    (0.3, 0.4, "普通"),
    (0.4, 0.6, "小污"),
    (0.6, 0.8, "大污"),
    (0.8, float("inf"), "非常污"),
)

# 五因子权重，合计 1.0。云型最重要：高云是幕布，低云挡住西边太阳。
WEIGHTS = {
    "cloud_layers": 0.35,
    "visibility": 0.20,
    "humidity": 0.15,
    "precip": 0.10,
    "total_cloud": 0.10,
    "aod": 0.10,
}

_LABELED_NUMBER = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)\s*[（(]([^)）]+)[)）]\s*$"
)


@dataclass(frozen=True)
class HourSample:
    time: str
    cloud_low: float
    cloud_mid: float
    cloud_high: float
    cloud_total: float
    visibility_m: float | None
    humidity: float | None
    precip_probability: float | None
    precipitation_mm: float | None
    aod: float | None


@dataclass(frozen=True)
class FactorScore:
    key: str
    name: str
    weight: float
    value: float
    detail: str


@dataclass(frozen=True)
class EngineResult:
    score_0_100: float
    grade: str
    p_visible: float
    p_worth_going: float
    factors: list[FactorScore] = field(default_factory=list)
    advice: str = ""


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def parse_labeled_number(text: str | None) -> tuple[float | None, str | None]:
    """解析 SunsetBot 的「0.163（小烧）」这类字段。"""
    if text is None:
        return None, None
    raw = str(text).strip()
    if not raw:
        return None, None
    match = _LABELED_NUMBER.match(raw)
    if match:
        return float(match.group(1)), match.group(2).strip()
    try:
        return float(raw), None
    except ValueError:
        return None, raw


def band_label(value: float, bands: tuple[tuple[float, float, str], ...]) -> str:
    for lo, hi, label in bands:
        if lo <= value < hi:
            return label
    return bands[-1][2]


def vividness_grade(value: float) -> str:
    return band_label(value, VIVIDNESS_BANDS)


def engine_grade(score_0_100: float) -> str:
    return band_label(score_0_100, ENGINE_GRADE_BANDS)


def aod_grade(value: float) -> str:
    return band_label(value, AOD_BANDS)


def _sigmoid(x: float) -> float:
    # 防溢出
    z = max(-40.0, min(40.0, x))
    return 1.0 / (1.0 + math.exp(-z))


def _plateau(x: float, rise_start: float, full_start: float, full_end: float, fall_end: float) -> float:
    """梯形得分：两端为 0，平台为 1。"""
    if x <= rise_start or x >= fall_end:
        return 0.0
    if full_start <= x <= full_end:
        return 1.0
    if x < full_start:
        width = full_start - rise_start
        return 0.0 if width <= 0 else (x - rise_start) / width
    width = fall_end - full_end
    return 0.0 if width <= 0 else (fall_end - x) / width


def score_high_canvas(high: float) -> float:
    """高云（卷云/卷积云）是火烧云的主要幕布。全无高云也能有淡晚霞，但很难「烧」。"""
    if high < 5:
        return 0.12
    # 90%+ 高云经常是一层灰盖，不再是透光卷云。
    return 0.12 + 0.88 * _plateau(high, 5.0, 22.0, 65.0, 90.0)


def score_mid_canvas(mid: float) -> float:
    """中云适量好看，过厚会挡光。"""
    if mid < 3:
        return 0.20
    return 0.20 + 0.80 * _plateau(mid, 3.0, 12.0, 40.0, 85.0)


def score_clear_horizon(low: float) -> float:
    """西边低云会挡住太阳光路。低云越少，越容易烧起来。"""
    if low <= 12:
        return 1.0
    if low >= 70:
        return 0.05
    return 1.0 - (low - 12.0) / (70.0 - 12.0) * 0.95


def score_cloud_layers(low: float, mid: float, high: float) -> tuple[float, str]:
    canvas = 0.70 * score_high_canvas(high) + 0.30 * score_mid_canvas(mid)
    horizon = score_clear_horizon(low)
    if high >= 90:
        canvas *= 0.35
    if (mid + high) >= 95:
        canvas *= 0.55
    # 既要有幕布，也要西边留光路；光路权重略高于「有没有云」。
    value = clamp(canvas * (0.35 + 0.65 * horizon))
    detail = (
        f"低云 {low:.0f}%（西边通透 {horizon:.0%}），"
        f"中云 {mid:.0f}%，高云 {high:.0f}%"
    )
    return value, detail


def score_visibility(visibility_m: float | None) -> tuple[float, str]:
    if visibility_m is None:
        return 0.45, "能见度缺失，按中性估计"
    km = visibility_m / 1000.0
    if km >= 25:
        value = 1.0
    elif km <= 2:
        value = 0.05
    else:
        value = 0.05 + 0.95 * (km - 2.0) / (23.0)
    return clamp(value), f"能见度 {km:.1f} km"


def score_humidity(humidity: float | None) -> tuple[float, str]:
    if humidity is None:
        return 0.50, "湿度缺失，按中性估计"
    # 40–65% 散射最好；太干颜色淡，太湿容易发灰/成雾。
    value = 0.18 + 0.82 * _plateau(humidity, 15.0, 40.0, 65.0, 96.0)
    return clamp(value), f"相对湿度 {humidity:.0f}%"


def score_precip(probability: float | None, mm: float | None) -> tuple[float, str]:
    pop = 0.0 if probability is None else clamp(probability / 100.0)
    rain = 0.0 if mm is None else max(0.0, mm)
    dry = 1.0 - min(1.0, pop / 0.55)
    if rain >= 0.2:
        dry *= 0.12
    elif rain > 0:
        dry *= 0.40
    detail = f"降水概率 {pop:.0%}"
    if mm is not None:
        detail += f"，该时次降水 {rain:.1f} mm"
    return clamp(dry), detail


def score_total_cloud(total: float, low: float, mid: float, high: float) -> tuple[float, str]:
    # 真正当幕布的是中高云。低云堆出来的总云量看起来「有云」，但烧不起来。
    canvas_cover = max(0.0, min(100.0, mid + high))
    if canvas_cover < 8:
        value = 0.18
    else:
        value = 0.15 + 0.85 * _plateau(canvas_cover, 8.0, 18.0, 60.0, 100.0)
    return clamp(value), f"总云量 {total:.0f}%，中高云幕布 {canvas_cover:.0f}%"


def score_aod(aod: float | None) -> tuple[float, str]:
    if aod is None:
        return 0.50, "AOD 缺失，按中性估计"
    if aod <= 0.22:
        value = 1.0
    elif aod >= 0.85:
        value = 0.06
    else:
        value = 1.0 - (aod - 0.22) / (0.85 - 0.22) * 0.94
    return clamp(value), f"AOD {aod:.3f}（{aod_grade(aod)}）"


def _pick_window(samples: list[HourSample], sunset_index: int) -> list[HourSample]:
    start = max(0, sunset_index - 1)
    end = min(len(samples), sunset_index + 2)
    return samples[start:end]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def score_hour_samples(samples: list[HourSample], sunset_index: int) -> EngineResult:
    if not samples:
        raise ValueError("没有可用于评分的小时样本")
    window = _pick_window(samples, sunset_index)
    sunset = samples[sunset_index]

    # 幕布看日落当小时 + 日落后一小时（火烧云经常在日落后更红）。
    # 西边遮挡看日落前 + 日落当小时。
    canvas_high = max(item.cloud_high for item in window)
    canvas_mid = max(item.cloud_mid for item in window)
    block_low = max(
        item.cloud_low
        for item in samples[max(0, sunset_index - 1) : sunset_index + 1]
    )
    total = sunset.cloud_total
    vis = sunset.visibility_m
    humidity = sunset.humidity
    pop = sunset.precip_probability
    mm = sunset.precipitation_mm
    aods = [item.aod for item in window if item.aod is not None]
    aod = _mean(aods) if aods else sunset.aod

    builders = (
        ("cloud_layers", "云型配置", score_cloud_layers(block_low, canvas_mid, canvas_high)),
        ("visibility", "能见度", score_visibility(vis)),
        ("humidity", "湿度", score_humidity(humidity)),
        ("precip", "降水", score_precip(pop, mm)),
        ("total_cloud", "总云量", score_total_cloud(total, block_low, canvas_mid, canvas_high)),
        ("aod", "气溶胶", score_aod(aod)),
    )
    factors: list[FactorScore] = []
    weighted = 0.0
    for key, name, (value, detail) in builders:
        weight = WEIGHTS[key]
        factors.append(
            FactorScore(key=key, name=name, weight=weight, value=value, detail=detail)
        )
        weighted += weight * value

    score_0_100 = round(100.0 * clamp(weighted), 1)
    vividness_eq = engine_score_to_vividness(score_0_100)
    p_visible, p_worth = engine_probabilities(score_0_100, vividness_eq)
    return EngineResult(
        score_0_100=score_0_100,
        grade=engine_grade(score_0_100),
        p_visible=p_visible,
        p_worth_going=p_worth,
        factors=factors,
        advice=advice_from_probs(p_visible, p_worth, vividness_eq),
    )


def engine_score_to_vividness(score_0_100: float) -> float:
    """把 0–100 引擎分粗映射到 SunsetBot 鲜艳度量纲，刻意保守。"""
    x = clamp(score_0_100 / 100.0)
    return round(1.15 * (x ** 2.35), 3)


def engine_probabilities(score_0_100: float, vividness: float) -> tuple[float, float]:
    """可见概率 / 值得出门概率。数值是校准过的模型估计，不是官方气候态频率。"""
    q = score_0_100 / 100.0
    p_visible = clamp(0.04 + 0.78 * _sigmoid((q - 0.42) / 0.13), 0.03, 0.84)
    p_worth = clamp(0.015 + 0.70 * _sigmoid((q - 0.60) / 0.12), 0.01, 0.72)
    if vividness < 0.02:
        p_visible = min(p_visible, 0.16)
        p_worth = min(p_worth, 0.05)
    return round(p_visible, 3), round(p_worth, 3)


def sunsetbot_probabilities(vividness: float) -> tuple[float, float]:
    """用 SunsetBot 鲜艳度做另一路概率。官方混淆矩阵未公开逐格数字，这里只做平滑映射。"""
    p_visible = clamp(0.04 + 0.82 * _sigmoid((vividness - 0.12) / 0.08), 0.03, 0.85)
    p_worth = clamp(0.02 + 0.76 * _sigmoid((vividness - 0.40) / 0.13), 0.015, 0.78)
    if vividness < 0.02:
        p_visible = min(p_visible, 0.12)
        p_worth = min(p_worth, 0.04)
    return round(p_visible, 3), round(p_worth, 3)


def combine_probabilities(
    engine: EngineResult,
    sunsetbot_vividness: float | None,
) -> tuple[float, float, float]:
    """综合两路概率。SunsetBot 用 GFS/CAMS 三维场，中国境内权重大一些。"""
    if sunsetbot_vividness is None:
        return engine.p_visible, engine.p_worth_going, 0.45
    sb_visible, sb_worth = sunsetbot_probabilities(sunsetbot_vividness)
    p_visible = round(0.72 * sb_visible + 0.28 * engine.p_visible, 3)
    p_worth = round(0.72 * sb_worth + 0.28 * engine.p_worth_going, 3)
    gap = abs(sb_visible - engine.p_visible)
    confidence = round(clamp(0.80 - gap * 0.85, 0.35, 0.86), 3)
    return p_visible, p_worth, confidence


def advice_from_probs(p_visible: float, p_worth: float, vividness: float) -> str:
    if p_worth >= 0.45 or vividness >= 0.4:
        return "建议出门，达到中烧以上的机会不低"
    if vividness < 0.02 and p_visible < 0.30:
        return "今晚大概率不烧"
    if vividness < 0.05 and p_visible < 0.35:
        return "大概率只有微烧，不值得专程跑"
    if p_visible >= 0.32 or vividness >= 0.15:
        return "可以顺便看一眼，预期是小烧级别"
    if vividness >= 0.04:
        return "大概率只有微烧，不值得专程跑"
    return "今晚大概率不烧"


def blend_vividness(gfs: float | None, ec: float | None) -> float | None:
    """晚霞以中午场次 GFS 更新更及时，GFS 权重大于 EC。"""
    if gfs is None and ec is None:
        return None
    if gfs is None:
        return ec
    if ec is None:
        return gfs
    return round(0.65 * gfs + 0.35 * ec, 3)
