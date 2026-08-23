"""把地点查询、官方评分和本地引擎串成一次预报。"""

from __future__ import annotations

from datetime import timedelta

from .clients import (
    ForecastError,
    GeoPlace,
    event_for_offset,
    cloudsea_sunrise_index,
    fetch_cloudsea_meteo,
    fetch_meteo,
    geocode,
    local_today,
    place_from_spot,
    query_sunsetbot,
)
from .cloudsea import pick_best_morning
from .report import CloudSeaDay, DayForecast, build_cloudsea_day, build_day_forecast
from .scoring import (
    advice_from_probs,
    blend_vividness,
    combine_probabilities,
    score_hour_samples,
)
from .spots import SPOTS, resolve_spot


def forecast_location(
    location: str,
    *,
    days: int = 2,
    models: tuple[str, ...] = ("GFS", "EC"),
) -> list[DayForecast]:
    if days < 1 or days > 7:
        raise ForecastError("days 必须在 1–7 之间")
    place = geocode(location)
    today = local_today(place.timezone)
    reports: list[DayForecast] = []
    for offset in range(days):
        target = today + timedelta(days=offset)
        meteo = fetch_meteo(place, target, forecast_days=max(days, 3))
        engine = score_hour_samples(meteo.samples, meteo.sunset_index)
        readings: dict = {}
        for model in models:
            if offset <= 1:
                try:
                    readings[model] = query_sunsetbot(
                        location,
                        event=event_for_offset(offset),
                        model=model,
                    )
                except ForecastError:
                    readings[model] = None
            else:
                readings[model] = None
        gfs = readings.get("GFS")
        ec = readings.get("EC")
        gfs_v = gfs.vividness if gfs is not None and gfs.status == "ok" else None
        ec_v = ec.vividness if ec is not None and ec.status == "ok" else None
        blended = blend_vividness(gfs_v, ec_v)
        p_visible, p_worth, confidence = combine_probabilities(engine, blended)
        advice = advice_from_probs(p_visible, p_worth, blended if blended is not None else 0.0)
        reports.append(
            build_day_forecast(
                day_offset=offset,
                target_date=target,
                location_input=location,
                place=place,
                sunset_local=meteo.sunset_local.isoformat(sep=" "),
                sunrise_local=meteo.sunrise_local.isoformat(sep=" "),
                readings=readings,
                engine=engine,
                blended_vividness=blended,
                p_visible=p_visible,
                p_worth=p_worth,
                confidence=confidence,
                advice=advice,
            )
        )
    return reports


def resolve_cloudsea_target(
    location: str,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    peak_m: float | None = None,
    valley_m: float | None = None,
) -> tuple[GeoPlace, float, float, str, str]:
    spot = resolve_spot(location)
    if spot is not None:
        return (
            place_from_spot(spot),
            float(peak_m if peak_m is not None else spot.peak_m),
            float(valley_m if valley_m is not None else spot.valley_m),
            spot.name,
            spot.note,
        )
    if latitude is None or longitude is None:
        known = "、".join(item.name for item in SPOTS)
        raise ForecastError(
            f"未收录观景点「{location}」。内置点：{known}。"
            "其它山头请加 --lat --lng --peak-m --valley-m。"
        )
    place = GeoPlace(
        name=location,
        latitude=float(latitude),
        longitude=float(longitude),
        timezone="Asia/Shanghai",
        country=None,
        admin1=None,
        population=0,
    )
    return (
        place,
        float(peak_m if peak_m is not None else 1000.0),
        float(valley_m if valley_m is not None else 80.0),
        location,
        "自定义经纬度。网格海拔不可靠，请确认 --peak-m / --valley-m。",
    )


def forecast_cloud_sea(
    location: str,
    *,
    days: int = 2,
    latitude: float | None = None,
    longitude: float | None = None,
    peak_m: float | None = None,
    valley_m: float | None = None,
) -> list[CloudSeaDay]:
    if days < 1 or days > 7:
        raise ForecastError("days 必须在 1–7 之间")
    place, peak, valley, spot_name, note = resolve_cloudsea_target(
        location,
        latitude=latitude,
        longitude=longitude,
        peak_m=peak_m,
        valley_m=valley_m,
    )
    today = local_today(place.timezone)
    bundle = fetch_cloudsea_meteo(
        place,
        today,
        peak_m=peak,
        valley_m=valley,
        spot_name=spot_name,
        forecast_days=max(days, 3),
    )
    reports: list[CloudSeaDay] = []
    for offset in range(days):
        target = today + timedelta(days=offset)
        result = pick_best_morning(
            bundle.samples,
            cloudsea_sunrise_index(bundle, target),
            peak_m=peak,
            valley_m=valley,
        )
        reports.append(
            build_cloudsea_day(
                day_offset=offset,
                target_date=target,
                location_input=location,
                spot_name=spot_name,
                note=note,
                place=place,
                peak_m=peak,
                valley_m=valley,
                sunrise_local=bundle.sunrises[target.isoformat()].isoformat(sep=" "),
                result=result,
            )
        )
    return reports
