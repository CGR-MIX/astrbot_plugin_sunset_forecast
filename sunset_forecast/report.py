"""把预报结果格式化成中文简报或 JSON。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from .clients import GeoPlace, SunsetBotReading
from .cloudsea import CloudSeaResult
from .scoring import EngineResult, FactorScore, vividness_grade


@dataclass
class CloudSeaDay:
    day_offset: int
    local_date: str
    location_input: str
    spot_name: str
    note: str
    place: dict[str, Any]
    peak_m: float
    valley_m: float
    sunrise_local: str
    sample_time: str
    p_appear: float
    grade: str
    advice: str
    score_0_100: float
    factors: list[dict[str, Any]]
    diagnostics: dict[str, Any]


@dataclass
class DayForecast:
    day_offset: int
    local_date: str
    location_input: str
    place: dict[str, Any]
    sunset_local: str
    sunrise_local: str
    sunsetbot: dict[str, Any]
    engine: dict[str, Any]
    combined: dict[str, Any]


def _reading_dict(reading: SunsetBotReading | None) -> dict[str, Any] | None:
    if reading is None:
        return None
    return {
        "status": reading.status,
        "query": reading.city_query,
        "display_city": reading.display_city,
        "model": reading.model,
        "event_time": reading.event_time,
        "times_name": reading.times_name,
        "times_str": reading.times_str,
        "quality_text": reading.quality_text,
        "aod_text": reading.aod_text,
        "vividness": reading.vividness,
        "vividness_label": reading.vividness_label,
        "aod": reading.aod,
        "aod_label": reading.aod_label,
    }


def _engine_dict(engine: EngineResult) -> dict[str, Any]:
    return {
        "score_0_100": engine.score_0_100,
        "grade": engine.grade,
        "p_visible": engine.p_visible,
        "p_worth_going": engine.p_worth_going,
        "advice": engine.advice,
        "factors": [asdict(item) for item in engine.factors],
    }


def _place_dict(place: GeoPlace) -> dict[str, Any]:
    return {
        "name": place.name,
        "admin1": place.admin1,
        "country": place.country,
        "latitude": place.latitude,
        "longitude": place.longitude,
        "timezone": place.timezone,
    }


def build_day_forecast(
    *,
    day_offset: int,
    target_date: date,
    location_input: str,
    place: GeoPlace,
    sunset_local: str,
    sunrise_local: str,
    readings: dict[str, SunsetBotReading | None],
    engine: EngineResult,
    blended_vividness: float | None,
    p_visible: float,
    p_worth: float,
    confidence: float,
    advice: str,
) -> DayForecast:
    return DayForecast(
        day_offset=day_offset,
        local_date=target_date.isoformat(),
        location_input=location_input,
        place=_place_dict(place),
        sunset_local=sunset_local,
        sunrise_local=sunrise_local,
        sunsetbot={
            "gfs": _reading_dict(readings.get("GFS")),
            "ec": _reading_dict(readings.get("EC")),
            "blended_vividness": blended_vividness,
            "blended_grade": None
            if blended_vividness is None
            else vividness_grade(blended_vividness),
        },
        engine=_engine_dict(engine),
        combined={
            "p_visible": p_visible,
            "p_worth_going": p_worth,
            "confidence": confidence,
            "advice": advice,
        },
    )


def build_cloudsea_day(
    *,
    day_offset: int,
    target_date: date,
    location_input: str,
    spot_name: str,
    note: str,
    place: GeoPlace,
    peak_m: float,
    valley_m: float,
    sunrise_local: str,
    result: CloudSeaResult,
) -> CloudSeaDay:
    return CloudSeaDay(
        day_offset=day_offset,
        local_date=target_date.isoformat(),
        location_input=location_input,
        spot_name=spot_name,
        note=note,
        place=_place_dict(place),
        peak_m=peak_m,
        valley_m=valley_m,
        sunrise_local=sunrise_local,
        sample_time=result.sample_time,
        p_appear=result.p_appear,
        grade=result.grade,
        advice=result.advice,
        score_0_100=result.score_0_100,
        factors=[asdict(item) for item in result.factors],
        diagnostics=dict(result.diagnostics),
    )


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _factor_line(factor: FactorScore) -> str:
    bar = int(round(factor.value * 10))
    meter = "█" * bar + "░" * (10 - bar)
    return f"  - {factor.name:4s} {meter} {factor.value * 100:5.1f}分  {factor.detail}"


def format_text(days: list[DayForecast]) -> str:
    if not days:
        return "没有预报结果。"
    first = days[0]
    place = first.place
    title = place["name"]
    if place.get("admin1") and place["admin1"] != title:
        title = f"{place['admin1']} {title}"
    lines = [
        f"晚霞预报  {title}  ({place['latitude']:.3f}, {place['longitude']:.3f})",
        "数据：SunsetBot GFS/EC + Open-Meteo 五因子引擎",
        "概率为模型估计，不是官方气候态频率；GFS 对晚霞常有漏报/空报。",
        "",
    ]
    for item in days:
        label = "今天" if item.day_offset == 0 else ("明天" if item.day_offset == 1 else f"{item.day_offset} 天后")
        combined = item.combined
        lines.append(f"【{label} {item.local_date}】日落 {item.sunset_local[11:16]}")
        gfs = item.sunsetbot.get("gfs") or {}
        ec = item.sunsetbot.get("ec") or {}
        if gfs.get("status") == "ok":
            lines.append(
                f"  SunsetBot GFS  鲜艳度 {gfs.get('quality_text') or '—'}  "
                f"AOD {gfs.get('aod_text') or '—'}  {gfs.get('times_name') or ''}"
            )
        elif gfs:
            lines.append(f"  SunsetBot GFS  未收录该地点（{gfs.get('status')}）")
        if ec.get("status") == "ok":
            lines.append(
                f"  SunsetBot EC   鲜艳度 {ec.get('quality_text') or '—'}  "
                f"AOD {ec.get('aod_text') or '—'}  {ec.get('times_name') or ''}"
            )
        blended = item.sunsetbot.get("blended_vividness")
        if blended is not None:
            lines.append(
                f"  综合鲜艳度 {blended:.3f}（{item.sunsetbot.get('blended_grade')}）"
            )
        engine = item.engine
        lines.append(
            f"  五因子评分 {engine['score_0_100']:.1f}/100（{engine['grade']}）"
        )
        for factor in engine["factors"]:
            lines.append(
                _factor_line(
                    FactorScore(
                        key=factor["key"],
                        name=factor["name"],
                        weight=factor["weight"],
                        value=factor["value"],
                        detail=factor["detail"],
                    )
                )
            )
        lines.append(
            f"  预测概率  能看见晚霞 {_pct(combined['p_visible'])}  "
            f"值得出门 {_pct(combined['p_worth_going'])}  "
            f"置信度 {_pct(combined['confidence'])}"
        )
        lines.append(f"  建议  {combined['advice']}")
        lines.append("")
    lines.append("等级对照：0.4 以上才比较值得出门，1.0 以上是典型大烧。")
    return "\n".join(lines).rstrip() + "\n"


def format_markdown(days: list[DayForecast]) -> str:
    """GitHub Actions job summary / README 片段用的 Markdown。"""
    if not days:
        return "没有预报结果。\n"
    first = days[0]
    place = first.place
    title = place["name"]
    if place.get("admin1") and place["admin1"] != title:
        title = f"{place['admin1']} {title}"
    lines = [
        f"## 晚霞预报 · {title}",
        "",
        f"`{place['latitude']:.3f}, {place['longitude']:.3f}` · "
        "SunsetBot GFS/EC + Open-Meteo 五因子",
        "",
        "概率是模型估计，不是官方气候态频率。",
        "",
    ]
    for item in days:
        label = (
            "今天"
            if item.day_offset == 0
            else ("明天" if item.day_offset == 1 else f"{item.day_offset} 天后")
        )
        gfs = item.sunsetbot.get("gfs") or {}
        ec = item.sunsetbot.get("ec") or {}
        combined = item.combined
        engine = item.engine
        lines.extend(
            [
                f"### {label} {item.local_date} · 日落 {item.sunset_local[11:16]}",
                "",
                "| 项目 | 结果 |",
                "| --- | --- |",
                f"| SunsetBot GFS | {gfs.get('quality_text') or '—'} / AOD {gfs.get('aod_text') or '—'} |",
                f"| SunsetBot EC | {ec.get('quality_text') or '—'} / AOD {ec.get('aod_text') or '—'} |",
                f"| 综合鲜艳度 | {item.sunsetbot.get('blended_vividness')}（{item.sunsetbot.get('blended_grade')}） |",
                f"| 五因子评分 | {engine['score_0_100']:.1f}/100（{engine['grade']}） |",
                f"| 能看见晚霞 | {_pct(combined['p_visible'])} |",
                f"| 值得出门 | {_pct(combined['p_worth_going'])} |",
                f"| 置信度 | {_pct(combined['confidence'])} |",
                f"| 建议 | {combined['advice']} |",
                "",
            ]
        )
        if engine.get("factors"):
            lines.append("<details><summary>五因子拆解</summary>")
            lines.append("")
            for factor in engine["factors"]:
                lines.append(
                    f"- {factor['name']} {factor['value'] * 100:.1f}分 — {factor['detail']}"
                )
            lines.append("")
            lines.append("</details>")
            lines.append("")
    lines.append("鲜艳度 0.4 以上才比较值得出门，1.0 以上是典型大烧。")
    lines.append("")
    return "\n".join(lines)


def format_cloudsea_text(days: list[CloudSeaDay]) -> str:
    if not days:
        return "没有云海预报结果。\n"
    first = days[0]
    lines = [
        f"云海预报  {first.spot_name}  观景 {first.peak_m:.0f} m / 山谷 {first.valley_m:.0f} m",
        f"{first.place.get('admin1') or ''} ({first.place['latitude']:.4f}, {first.place['longitude']:.4f})",
        first.note,
        "依据：山下饱和层云/辐射雾 + 山顶出云 + 逆温。概率为模型估计。",
        "",
    ]
    for item in days:
        label = (
            "今天"
            if item.day_offset == 0
            else ("明天" if item.day_offset == 1 else f"{item.day_offset} 天后")
        )
        hour = item.sample_time[11:16] if len(item.sample_time) >= 16 else item.sample_time
        lines.append(
            f"【{label} {item.local_date}】日出 {item.sunrise_local[11:16]}  最佳时次 {hour}"
        )
        lines.append(
            f"  出现概率 {_pct(item.p_appear)}（{item.grade}）  评分 {item.score_0_100:.1f}/100"
        )
        diag = item.diagnostics
        bits = []
        if diag.get("rh_valley") is not None:
            bits.append(f"山谷湿度 {diag['rh_valley']:.0f}%")
        if diag.get("rh_peak") is not None:
            bits.append(f"山顶湿度 {diag['rh_peak']:.0f}%")
        if diag.get("cloud_base_m") is not None:
            bits.append(f"云底 {diag['cloud_base_m']:.0f} m")
        if bits:
            lines.append("  " + "  ".join(bits))
        for factor in item.factors:
            lines.append(
                _factor_line(
                    FactorScore(
                        key=factor["key"],
                        name=factor["name"],
                        weight=factor["weight"],
                        value=factor["value"],
                        detail=factor["detail"],
                    )
                )
            )
        lines.append(f"  建议  {item.advice}")
        lines.append("")
    lines.append("看云海请赶日出前后；山顶湿度 ≥94% 通常是人在云中，不是站在云上。")
    return "\n".join(lines).rstrip() + "\n"


def format_cloudsea_markdown(days: list[CloudSeaDay]) -> str:
    if not days:
        return "没有云海预报结果。\n"
    first = days[0]
    lines = [
        f"## 云海预报 · {first.spot_name}",
        "",
        f"观景 {first.peak_m:.0f} m · 山谷 {first.valley_m:.0f} m · "
        f"`{first.place['latitude']:.4f}, {first.place['longitude']:.4f}`",
        "",
        first.note,
        "",
        "概率是模型估计：山下成云、山顶出云、中间最好有逆温。",
        "",
    ]
    for item in days:
        label = (
            "今天"
            if item.day_offset == 0
            else ("明天" if item.day_offset == 1 else f"{item.day_offset} 天后")
        )
        hour = item.sample_time[11:16] if len(item.sample_time) >= 16 else item.sample_time
        lines.extend(
            [
                f"### {label} {item.local_date} · 日出 {item.sunrise_local[11:16]} · 时次 {hour}",
                "",
                "| 项目 | 结果 |",
                "| --- | --- |",
                f"| 出现概率 | {_pct(item.p_appear)}（{item.grade}） |",
                f"| 评分 | {item.score_0_100:.1f}/100 |",
                f"| 山谷湿度 | {item.diagnostics.get('rh_valley')}% |",
                f"| 山顶湿度 | {item.diagnostics.get('rh_peak')}% |",
                f"| 云底 | {item.diagnostics.get('cloud_base_m')} m |",
                f"| 建议 | {item.advice} |",
                "",
            ]
        )
        if item.factors:
            lines.append("<details><summary>因子拆解</summary>")
            lines.append("")
            for factor in item.factors:
                lines.append(
                    f"- {factor['name']} {factor['value'] * 100:.1f}分 — {factor['detail']}"
                )
            lines.append("")
            lines.append("</details>")
            lines.append("")
    lines.append("山顶湿度 ≥94% 时，人多半在云里而不是云上。")
    lines.append("")
    return "\n".join(lines)


def format_sunset_chat(days: list[DayForecast]) -> str:
    """QQ / AstrBot 用的短消息，不含因子条。"""
    if not days:
        return "没有晚霞预报。"
    first = days[0]
    title = first.place["name"]
    admin = first.place.get("admin1")
    if admin and admin != title:
        title = f"{admin} {title}"
    lines = [f"🌇 {title}晚霞"]
    for item in days:
        label = "今天" if item.day_offset == 0 else ("明天" if item.day_offset == 1 else f"{item.day_offset}天后")
        gfs = item.sunsetbot.get("gfs") or {}
        quality = gfs.get("quality_text") or "—"
        aod = gfs.get("aod_text") or "—"
        combined = item.combined
        lines.append(
            f"{label} {item.local_date[5:]} 日落 {item.sunset_local[11:16]}\n"
            f"GFS {quality}  AOD {aod}\n"
            f"能看见 {_pct(combined['p_visible'])} · 值得出门 {_pct(combined['p_worth_going'])}\n"
            f"{combined['advice']}"
        )
    return "\n\n".join(lines)


def format_cloudsea_chat(days: list[CloudSeaDay]) -> str:
    """QQ / AstrBot 用的短消息。"""
    if not days:
        return "没有云海预报。"
    first = days[0]
    lines = [f"🏔️ {first.spot_name}云海  观景 {first.peak_m:.0f}m"]
    for item in days:
        label = "今天" if item.day_offset == 0 else ("明天" if item.day_offset == 1 else f"{item.day_offset}天后")
        hour = item.sample_time[11:16] if len(item.sample_time) >= 16 else item.sample_time
        diag = item.diagnostics
        extra = []
        if diag.get("rh_valley") is not None:
            extra.append(f"山谷湿度 {diag['rh_valley']:.0f}%")
        if diag.get("rh_peak") is not None:
            extra.append(f"山顶湿度 {diag['rh_peak']:.0f}%")
        lines.append(
            f"{label} {item.local_date[5:]} 日出 {item.sunrise_local[11:16]}（{hour}）\n"
            f"出现概率 {_pct(item.p_appear)}（{item.grade}）\n"
            + (" · ".join(extra) + "\n" if extra else "")
            + item.advice
        )
    return "\n\n".join(lines)
