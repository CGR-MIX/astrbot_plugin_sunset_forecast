"""高山云海出现概率。

物理图像（北京高山云海、景区云海专利的共同结论）：
山下饱和成层云/辐射雾，山顶相对干燥能看下去，中间最好有逆温把水汽按住。

观景概率用 Open-Meteo 地面 + 1000–800 hPa 层结估计，不是官方气候态频率。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .scoring import FactorScore, _plateau, clamp

# 权重合计 1.0。山下成云和山顶出云最关键。
WEIGHTS = {
    "valley_moisture": 0.28,
    "peak_clear": 0.24,
    "deck_geometry": 0.20,
    "inversion": 0.14,
    "wind": 0.08,
    "precip": 0.06,
}

CLOUDSEA_GRADE_BANDS: tuple[tuple[float, float, str], ...] = (
    (0.0, 0.12, "难见"),
    (0.12, 0.28, "局部薄雾"),
    (0.28, 0.45, "有机会"),
    (0.45, 0.62, "较明显"),
    (0.62, 0.78, "成海机会高"),
    (0.78, 1.01, "条件很好"),
)

PRESSURE_LEVELS: tuple[int, ...] = (1000, 975, 950, 925, 900, 850, 800)


@dataclass(frozen=True)
class PressureLevel:
    hpa: int
    height_m: float
    temperature_c: float | None
    rh: float | None
    cloud: float | None
    wind_ms: float | None


@dataclass(frozen=True)
class CloudSeaSample:
    time: str
    temperature_2m: float | None
    dew_point_2m: float | None
    humidity_2m: float | None
    cloud_low: float
    cloud_mid: float
    cloud_high: float
    cloud_total: float
    visibility_m: float | None
    precip_mm: float | None
    precip_probability: float | None
    wind_10m_ms: float | None
    levels: tuple[PressureLevel, ...]


@dataclass(frozen=True)
class CloudSeaResult:
    score_0_100: float
    p_appear: float
    grade: str
    advice: str
    sample_time: str
    factors: list[FactorScore] = field(default_factory=list)
    diagnostics: dict[str, float | str | None] = field(default_factory=dict)


def cloudsea_grade(probability: float) -> str:
    for lo, hi, label in CLOUDSEA_GRADE_BANDS:
        if lo <= probability < hi:
            return label
    return CLOUDSEA_GRADE_BANDS[-1][2]


def field_at_height(
    levels: tuple[PressureLevel, ...] | list[PressureLevel],
    height_m: float,
    attr: str,
) -> float | None:
    points: list[tuple[float, float]] = []
    for level in levels:
        value = getattr(level, attr)
        if value is None:
            continue
        points.append((level.height_m, float(value)))
    points.sort()
    if not points:
        return None
    if height_m <= points[0][0]:
        return points[0][1]
    if height_m >= points[-1][0]:
        return points[-1][1]
    for (z0, v0), (z1, v1) in zip(points, points[1:]):
        if z0 <= height_m <= z1:
            if z1 == z0:
                return v0
            t = (height_m - z0) / (z1 - z0)
            return v0 + t * (v1 - v0)
    return None


def layer_mean(
    levels: tuple[PressureLevel, ...] | list[PressureLevel],
    zmin: float,
    zmax: float,
    attr: str,
) -> float | None:
    values = [
        float(getattr(level, attr))
        for level in levels
        if getattr(level, attr) is not None and zmin <= level.height_m <= zmax
    ]
    if values:
        return sum(values) / len(values)
    return field_at_height(levels, (zmin + zmax) / 2.0, attr)


def estimate_cloud_base_m(
    levels: tuple[PressureLevel, ...] | list[PressureLevel],
    humidity_2m: float | None,
    valley_m: float,
) -> float | None:
    """从下往上找相对湿度 >= 84% 的第一层，近似云底/雾顶起始高度。"""
    ordered = sorted(levels, key=lambda item: item.height_m)
    if humidity_2m is not None and humidity_2m >= 92:
        return valley_m
    for level in ordered:
        if level.rh is not None and level.rh >= 84 and level.height_m >= valley_m - 40:
            return level.height_m
    return None


def estimate_lcl_m(
    temperature_2m: float | None,
    dew_point_2m: float | None,
    surface_m: float,
) -> float | None:
    if temperature_2m is None or dew_point_2m is None:
        return None
    # 常用近似：抬升凝结高度（米）≈ 125 × (T − Td)
    return max(0.0, surface_m + 125.0 * (temperature_2m - dew_point_2m))


def score_valley_moisture(
    rh_valley: float | None,
    humidity_2m: float | None,
    cloud_low: float,
) -> tuple[float, str]:
    pieces = [item for item in (rh_valley, humidity_2m) if item is not None]
    rh = sum(pieces) / len(pieces) if pieces else 50.0
    if rh < 55:
        wet = 0.08
    elif rh >= 90:
        wet = 1.0
    else:
        wet = 0.08 + 0.92 * (rh - 55.0) / 35.0
    cloud_term = 0.30 + 0.70 * _plateau(cloud_low, 0.0, 30.0, 95.0, 110.0)
    value = clamp(max(wet, 0.62 * wet + 0.38 * cloud_term))
    return value, f"山谷相对湿度 {rh:.0f}%，低云 {cloud_low:.0f}%"


def score_peak_clear(rh_peak: float | None, cloud_peak: float | None) -> tuple[float, str]:
    if rh_peak is None:
        return 0.45, "山顶湿度缺失，按中性估计"
    if rh_peak >= 94:
        value = 0.05
    elif rh_peak >= 90:
        value = 0.12
    elif rh_peak >= 84:
        value = 0.12 + (90.0 - rh_peak) / 6.0 * 0.38
    elif rh_peak <= 68:
        value = 1.0
    else:
        value = 0.50 + (84.0 - rh_peak) / 16.0 * 0.50
    if cloud_peak is not None and cloud_peak >= 70:
        value *= 0.50
    elif cloud_peak is not None and cloud_peak >= 40:
        value *= 0.75
    return clamp(value), f"山顶相对湿度 {rh_peak:.0f}%" + (
        f"，该层云量 {cloud_peak:.0f}%" if cloud_peak is not None else ""
    )


def score_deck_geometry(
    cloud_base_m: float | None,
    peak_m: float,
    valley_m: float,
    rh_peak: float | None,
) -> tuple[float, str]:
    if cloud_base_m is None:
        return 0.12, "垂直方向没有饱和层，难铺成云海"
    if rh_peak is not None and rh_peak >= 90:
        return 0.10, f"云底约 {cloud_base_m:.0f} m，山顶湿度 {rh_peak:.0f}%，人容易在云中"
    if cloud_base_m > peak_m - 60:
        return 0.16, f"云底 {cloud_base_m:.0f} m，接近或高于观景面 {peak_m:.0f} m"
    thickness = peak_m - cloud_base_m
    if thickness < 120:
        value = 0.35
        detail = f"云底 {cloud_base_m:.0f} m，厚度只有 {thickness:.0f} m，偏薄"
    elif cloud_base_m < valley_m + 40 and thickness > 900:
        value = 0.55
        detail = f"云底贴地（约 {cloud_base_m:.0f} m），要确认山顶是否露出来"
    else:
        value = 0.55 + 0.45 * _plateau(thickness, 120.0, 250.0, 900.0, 1400.0)
        detail = f"云底约 {cloud_base_m:.0f} m，观景面 {peak_m:.0f} m，厚度 {thickness:.0f} m"
    return clamp(value), detail


def score_inversion(
    t_valley: float | None,
    t_peak: float | None,
    valley_z: float,
    peak_z: float,
) -> tuple[float, str]:
    if t_valley is None or t_peak is None:
        return 0.45, "温度廓线缺失，按中性估计"
    dz = max(80.0, peak_z - valley_z)
    lapse = (t_valley - t_peak) / dz * 1000.0
    # 标准直减率约 6.5 K/km；接近 0 或负值是逆温，有利于把水汽按在山下。
    if lapse <= 1.0:
        value = 1.0
    elif lapse >= 8.5:
        value = 0.12
    else:
        value = 1.0 - (lapse - 1.0) / 7.5 * 0.88
    return clamp(value), f"层结直减率 {lapse:.1f} K/km（越小越稳，负值=逆温）"


def score_wind(wind_ms: float | None) -> tuple[float, str]:
    if wind_ms is None:
        return 0.50, "风速缺失，按中性估计"
    if wind_ms <= 3.5:
        value = 1.0
    elif wind_ms >= 10.0:
        value = 0.08
    else:
        value = 1.0 - (wind_ms - 3.5) / 6.5 * 0.92
    return clamp(value), f"近地面/低层风速 {wind_ms:.1f} m/s"


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
        detail += f"，该时次 {rain:.1f} mm"
    return clamp(dry), detail


def _advice(p_appear: float, rh_peak: float | None) -> str:
    if rh_peak is not None and rh_peak >= 90 and p_appear < 0.40:
        return "山顶很可能在云里，上去也看不见海"
    if p_appear >= 0.65:
        return "建议上山，成海条件较好"
    if p_appear >= 0.45:
        return "值得一碰，可能是局部或偏薄的云海"
    if p_appear >= 0.28:
        return "机会一般，不专程跑也行"
    if p_appear >= 0.15:
        return "多半只有薄雾或碎云"
    return "基本没有云海"


def score_cloud_sea_sample(
    sample: CloudSeaSample,
    *,
    peak_m: float,
    valley_m: float,
) -> CloudSeaResult:
    valley_top = max(valley_m + 80.0, peak_m - 250.0)
    rh_valley = layer_mean(sample.levels, valley_m, valley_top, "rh")
    t_valley = layer_mean(sample.levels, valley_m, valley_top, "temperature_c")
    rh_peak = field_at_height(sample.levels, peak_m, "rh")
    t_peak = field_at_height(sample.levels, peak_m, "temperature_c")
    cloud_peak = field_at_height(sample.levels, peak_m, "cloud")
    valley_z = min(
        (level.height_m for level in sample.levels if level.height_m >= valley_m),
        default=valley_m,
    )
    wind = sample.wind_10m_ms
    if wind is None:
        low_winds = [
            level.wind_ms
            for level in sample.levels
            if level.wind_ms is not None and level.height_m <= valley_m + 400
        ]
        wind = sum(low_winds) / len(low_winds) if low_winds else None

    cloud_base = estimate_cloud_base_m(sample.levels, sample.humidity_2m, valley_m)
    surface_m = min((level.height_m for level in sample.levels), default=0.0)
    lcl_m = estimate_lcl_m(sample.temperature_2m, sample.dew_point_2m, surface_m)

    builders = (
        (
            "valley_moisture",
            "山下水汽",
            score_valley_moisture(rh_valley, sample.humidity_2m, sample.cloud_low),
        ),
        ("peak_clear", "山顶出云", score_peak_clear(rh_peak, cloud_peak)),
        (
            "deck_geometry",
            "云海厚度",
            score_deck_geometry(cloud_base, peak_m, valley_m, rh_peak),
        ),
        (
            "inversion",
            "层结稳定",
            score_inversion(t_valley, t_peak, valley_z, peak_m),
        ),
        ("wind", "风速", score_wind(wind)),
        ("precip", "降水", score_precip(sample.precip_probability, sample.precip_mm)),
    )
    factors: list[FactorScore] = []
    for key, name, (value, detail) in builders:
        factors.append(
            FactorScore(key=key, name=name, weight=WEIGHTS[key], value=value, detail=detail)
        )

    # 加权分只作拆解展示。出现概率用「山下成云 × 山顶出云」结构，
    # 避免整层都湿时还被风速/水汽拉成「条件很好」。
    valley = next(item.value for item in factors if item.key == "valley_moisture")
    peak = next(item.value for item in factors if item.key == "peak_clear")
    deck = next(item.value for item in factors if item.key == "deck_geometry")
    inversion = next(item.value for item in factors if item.key == "inversion")
    wind_v = next(item.value for item in factors if item.key == "wind")
    precip_v = next(item.value for item in factors if item.key == "precip")
    p_struct = clamp(valley * (0.25 + 0.75 * peak) * (0.35 + 0.65 * deck))
    p_support = clamp(0.50 * inversion + 0.30 * wind_v + 0.20 * precip_v)
    p_appear = clamp(p_struct * (0.55 + 0.45 * p_support), 0.03, 0.86)
    if rh_peak is not None and rh_peak >= 94:
        p_appear = min(p_appear, 0.16)
    elif rh_peak is not None and rh_peak >= 90:
        p_appear = min(p_appear, 0.26)
    if sample.precip_mm is not None and sample.precip_mm >= 0.2:
        p_appear = min(p_appear, 0.16)
    p_appear = round(p_appear, 3)
    score_0_100 = round(100.0 * p_appear, 1)
    return CloudSeaResult(
        score_0_100=score_0_100,
        p_appear=p_appear,
        grade=cloudsea_grade(p_appear),
        advice=_advice(p_appear, rh_peak),
        sample_time=sample.time,
        factors=factors,
        diagnostics={
            "rh_valley": None if rh_valley is None else round(rh_valley, 1),
            "rh_peak": None if rh_peak is None else round(rh_peak, 1),
            "cloud_base_m": None if cloud_base is None else round(cloud_base, 0),
            "lcl_m": None if lcl_m is None else round(lcl_m, 0),
            "peak_m": peak_m,
            "valley_m": valley_m,
        },
    )


def pick_best_morning(
    samples: list[CloudSeaSample],
    sunrise_index: int,
    *,
    peak_m: float,
    valley_m: float,
) -> CloudSeaResult:
    start = max(0, sunrise_index - 1)
    end = min(len(samples), sunrise_index + 2)
    window = samples[start:end] or samples[sunrise_index : sunrise_index + 1]
    scored = [
        score_cloud_sea_sample(item, peak_m=peak_m, valley_m=valley_m) for item in window
    ]
    return max(scored, key=lambda item: item.p_appear)
