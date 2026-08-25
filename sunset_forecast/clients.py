"""SunsetBot 与 Open-Meteo 客户端。仅使用标准库。"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .cloudsea import PRESSURE_LEVELS, CloudSeaSample, PressureLevel
from .places import (
    city_key,
    geocode_query_variants,
    lookup_china_city,
    sunsetbot_query_city,
)
from .scoring import HourSample, parse_labeled_number
from .spots import ViewSpot

USER_AGENT = "sunset-forecast/1.0 (+local; personal use)"
SUNSETBOT_URL = "https://sunsetbot.top/"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

EVENT_TODAY = "set_1"
EVENT_TOMORROW = "set_2"


class ForecastError(RuntimeError):
    pass


@dataclass(frozen=True)
class GeoPlace:
    name: str
    latitude: float
    longitude: float
    timezone: str
    country: str | None
    admin1: str | None
    population: int


@dataclass(frozen=True)
class SunsetBotReading:
    city_query: str
    display_city: str
    model: str
    event: str
    event_time: str
    times_name: str
    times_str: str
    quality_text: str
    aod_text: str
    vividness: float | None
    vividness_label: str | None
    aod: float | None
    aod_label: str | None
    status: str
    summary: str


@dataclass(frozen=True)
class MeteoBundle:
    place: GeoPlace
    sunset_local: datetime
    sunrise_local: datetime
    samples: list[HourSample]
    sunset_index: int


@dataclass(frozen=True)
class CloudSeaBundle:
    place: GeoPlace
    spot_name: str
    peak_m: float
    valley_m: float
    sunrises: dict[str, datetime]
    sunsets: dict[str, datetime]
    samples: list[CloudSeaSample]


def http_get_json(url: str, timeout: int = 8, retries: int = 2) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            last_error = exc
            # 4xx 里只有 429 值得重试；其它直接失败。
            if exc.code < 500 and exc.code != 429:
                raise ForecastError(f"HTTP {exc.code}：{url}") from exc
        except urllib.error.URLError as exc:
            last_error = exc
        except json.JSONDecodeError as exc:
            last_error = exc
        except TimeoutError as exc:
            last_error = exc
        if attempt < retries:
            time.sleep(1.2 * attempt)
    raise ForecastError(
        f"请求失败（{retries} 次）：{url}；最后错误：{last_error}"
    ) from last_error


def _city_candidates(location: str) -> list[str]:
    name = location.strip()
    mapped = sunsetbot_query_city(location) if name else ""
    if not name and not mapped:
        raise ForecastError("地点不能为空")
    candidates: list[str] = []
    for item in (mapped, name):
        item = (item or "").strip()
        if not item:
            continue
        candidates.append(item)
        if item.endswith("市") and len(item) > 2:
            candidates.append(item[:-1])
        if item.endswith("省") and len(item) > 2:
            candidates.append(item[:-1])
        if "-" in item:
            candidates.append(item.split("-")[-1])
            candidates.append(item.split("-")[0])
    if mapped == "肇庆":
        candidates.insert(1, "广东-肇庆")
    # SunsetBot 的「端州」是朝鲜端州，不是肇庆端州区。
    seen: set[str] = set()
    unique: list[str] = []
    for item in candidates:
        item = item.strip()
        if not item or item == "端州" or item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique or ["肇庆"]


def query_sunsetbot(
    location: str,
    *,
    event: str = EVENT_TODAY,
    model: str = "GFS",
) -> SunsetBotReading:
    last_not_found: SunsetBotReading | None = None
    for city in _city_candidates(location):
        params = urllib.parse.urlencode(
            {
                "query_id": str(random.randint(100000, 999999)),
                "intend": "select_city",
                "query_city": city,
                "event_date": "None",
                "event": event,
                "times": "None",
                "model": model,
            }
        )
        payload = http_get_json(f"{SUNSETBOT_URL}?{params}", timeout=8, retries=1)
        status = str(payload.get("status") or "")
        quality_text = str(payload.get("tb_quality") or "")
        aod_text = str(payload.get("tb_aod") or "")
        vividness, vividness_label = parse_labeled_number(quality_text)
        aod, aod_label = parse_labeled_number(aod_text)
        reading = SunsetBotReading(
            city_query=city,
            display_city=str(payload.get("display_city_name") or city),
            model=str(payload.get("display_model") or model),
            event=event,
            event_time=str(payload.get("tb_event_time") or ""),
            times_name=str(payload.get("display_times_name") or ""),
            times_str=str(payload.get("display_times_str") or ""),
            quality_text=quality_text,
            aod_text=aod_text,
            vividness=vividness,
            vividness_label=vividness_label,
            aod=aod,
            aod_label=aod_label,
            status=status,
            summary=str(payload.get("img_summary") or payload.get("place_holder") or ""),
        )
        if status == "ok":
            return reading
        last_not_found = reading
    if last_not_found is not None:
        return last_not_found
    raise ForecastError(f"SunsetBot 未返回数据：{location}")


def place_from_spot(spot: ViewSpot) -> GeoPlace:
    return GeoPlace(
        name=spot.name,
        latitude=spot.latitude,
        longitude=spot.longitude,
        timezone=spot.timezone,
        country="中国",
        admin1=spot.admin1,
        population=0,
    )


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def lookup_builtin_city(location: str) -> GeoPlace | None:
    hit = lookup_china_city(location)
    if hit is None:
        return None
    lat, lng, admin1, display = hit
    return GeoPlace(
        name=display,
        latitude=lat,
        longitude=lng,
        timezone="Asia/Shanghai",
        country="中国",
        admin1=admin1,
        population=0,
    )


def _openmeteo_geocode(location: str) -> GeoPlace | None:
    for query in geocode_query_variants(location):
        params = urllib.parse.urlencode(
            {
                "name": query,
                "count": 8,
                "language": "zh",
                "format": "json",
            }
        )
        payload = http_get_json(f"{GEOCODE_URL}?{params}")
        results = payload.get("results") or []
        if not results:
            continue

        def rank(item: dict[str, Any]) -> tuple[int, int, int]:
            country_boost = 1 if item.get("country_code") in {"CN", "HK", "MO", "TW"} else 0
            population = int(item.get("population") or 0)
            name = str(item.get("name") or "")
            exact = 1 if city_key(name) == city_key(location) else 0
            return (country_boost, exact, population)

        best = max(results, key=rank)
        cc = str(best.get("country_code") or "")
        if cc not in {"CN", "HK", "MO", "TW"}:
            continue
        return GeoPlace(
            name=str(best.get("name") or location),
            latitude=float(best["latitude"]),
            longitude=float(best["longitude"]),
            timezone=str(best.get("timezone") or "Asia/Shanghai"),
            country=best.get("country"),
            admin1=best.get("admin1"),
            population=int(best.get("population") or 0),
        )
    return None


def _nominatim_china(location: str) -> GeoPlace | None:
    params = urllib.parse.urlencode(
        {
            "q": f"{location},中国",
            "format": "json",
            "limit": 5,
            "countrycodes": "cn,hk,mo,tw",
            "accept-language": "zh",
        }
    )
    try:
        payload = http_get_json(f"{NOMINATIM_URL}?{params}", timeout=8, retries=1)
    except ForecastError:
        return None
    if not isinstance(payload, list) or not payload:
        return None
    best = payload[0]
    try:
        lat = float(best["lat"])
        lng = float(best["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    display = str(best.get("name") or location)
    return GeoPlace(
        name=city_key(location) or display,
        latitude=lat,
        longitude=lng,
        timezone="Asia/Shanghai",
        country="中国",
        admin1=None,
        population=0,
    )


def geocode(location: str) -> GeoPlace:
    builtin = lookup_builtin_city(location)
    if builtin is not None:
        return builtin
    remote = _openmeteo_geocode(location)
    if remote is not None:
        return remote
    nominatim = _nominatim_china(location)
    if nominatim is not None:
        return nominatim
    raise ForecastError(
        f"找不到地点：{location}。请用国内城市或区县名，例如「肇庆」「拉萨」「喀什」。"
    )


def _parse_local(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _nearest_hour_index(times: list[str], target: datetime) -> int:
    best_i = 0
    best_delta = None
    for i, stamp in enumerate(times):
        current = _parse_local(stamp)
        delta = abs((current - target).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_i = i
    return best_i


@dataclass(frozen=True)
class MeteoSeries:
    place: GeoPlace
    samples: list[HourSample]
    sunrises: dict[str, datetime]
    sunsets: dict[str, datetime]


def fetch_meteo_series(place: GeoPlace, forecast_days: int = 3) -> MeteoSeries:
    forecast_params = urllib.parse.urlencode(
        {
            "latitude": f"{place.latitude:.5f}",
            "longitude": f"{place.longitude:.5f}",
            "hourly": ",".join(
                [
                    "cloud_cover",
                    "cloud_cover_low",
                    "cloud_cover_mid",
                    "cloud_cover_high",
                    "visibility",
                    "relative_humidity_2m",
                    "precipitation_probability",
                    "precipitation",
                ]
            ),
            "daily": "sunrise,sunset",
            "timezone": place.timezone,
            "forecast_days": str(max(forecast_days, 1)),
        }
    )
    air_params = urllib.parse.urlencode(
        {
            "latitude": f"{place.latitude:.5f}",
            "longitude": f"{place.longitude:.5f}",
            "hourly": "aerosol_optical_depth",
            "timezone": place.timezone,
            "forecast_days": str(max(forecast_days, 1)),
        }
    )

    def _air() -> dict[str, float]:
        try:
            air = http_get_json(f"{AIR_URL}?{air_params}")
        except ForecastError:
            return {}
        hourly_air = air.get("hourly") or {}
        out: dict[str, float] = {}
        for stamp, value in zip(
            hourly_air.get("time") or [],
            hourly_air.get("aerosol_optical_depth") or [],
        ):
            if value is not None:
                out[stamp] = float(value)
        return out

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_forecast = pool.submit(http_get_json, f"{FORECAST_URL}?{forecast_params}")
        fut_air = pool.submit(_air)
        forecast = fut_forecast.result()
        aod_by_time = fut_air.result()

    daily = forecast.get("daily") or {}
    dates = daily.get("time") or []
    sunrises = {
        day: _parse_local(stamp)
        for day, stamp in zip(dates, daily.get("sunrise") or [])
    }
    sunsets = {
        day: _parse_local(stamp)
        for day, stamp in zip(dates, daily.get("sunset") or [])
    }
    hourly = forecast.get("hourly") or {}
    times = hourly.get("time") or []
    samples: list[HourSample] = []
    for i, stamp in enumerate(times):
        samples.append(
            HourSample(
                time=stamp,
                cloud_low=_num(hourly.get("cloud_cover_low"), i),
                cloud_mid=_num(hourly.get("cloud_cover_mid"), i),
                cloud_high=_num(hourly.get("cloud_cover_high"), i),
                cloud_total=_num(hourly.get("cloud_cover"), i),
                visibility_m=_optional_num(hourly.get("visibility"), i),
                humidity=_optional_num(hourly.get("relative_humidity_2m"), i),
                precip_probability=_optional_num(hourly.get("precipitation_probability"), i),
                precipitation_mm=_optional_num(hourly.get("precipitation"), i),
                aod=aod_by_time.get(stamp),
            )
        )
    if not samples:
        raise ForecastError("Open-Meteo 没有小时云量数据")
    return MeteoSeries(place=place, samples=samples, sunrises=sunrises, sunsets=sunsets)


def slice_meteo(series: MeteoSeries, target_date: date) -> MeteoBundle:
    key = target_date.isoformat()
    if key not in series.sunsets:
        raise ForecastError(f"Open-Meteo 没有 {key} 的日落数据")
    sunset_local = series.sunsets[key]
    sunrise_local = series.sunrises[key]
    times = [item.time for item in series.samples]
    return MeteoBundle(
        place=series.place,
        sunset_local=sunset_local,
        sunrise_local=sunrise_local,
        samples=series.samples,
        sunset_index=_nearest_hour_index(times, sunset_local),
    )


def fetch_meteo(place: GeoPlace, target_date: date, forecast_days: int = 3) -> MeteoBundle:
    series = fetch_meteo_series(place, forecast_days=forecast_days)
    return slice_meteo(series, target_date)


def fetch_cloudsea_meteo(
    place: GeoPlace,
    target_date: date,
    *,
    peak_m: float,
    valley_m: float,
    spot_name: str,
    forecast_days: int = 3,
) -> CloudSeaBundle:
    level_vars: list[str] = []
    for hpa in PRESSURE_LEVELS:
        level_vars.extend(
            [
                f"temperature_{hpa}hPa",
                f"relative_humidity_{hpa}hPa",
                f"cloud_cover_{hpa}hPa",
                f"wind_speed_{hpa}hPa",
                f"geopotential_height_{hpa}hPa",
            ]
        )
    hourly = [
        "temperature_2m",
        "dew_point_2m",
        "relative_humidity_2m",
        "cloud_cover",
        "cloud_cover_low",
        "cloud_cover_mid",
        "cloud_cover_high",
        "visibility",
        "precipitation",
        "precipitation_probability",
        "wind_speed_10m",
        *level_vars,
    ]
    params = urllib.parse.urlencode(
        {
            "latitude": f"{place.latitude:.5f}",
            "longitude": f"{place.longitude:.5f}",
            "hourly": ",".join(hourly),
            "daily": "sunrise,sunset",
            "timezone": place.timezone,
            "forecast_days": str(max(forecast_days, 1)),
            "wind_speed_unit": "ms",
        }
    )
    payload = http_get_json(f"{FORECAST_URL}?{params}")
    daily = payload.get("daily") or {}
    dates = daily.get("time") or []
    if target_date.isoformat() not in dates:
        raise ForecastError(f"Open-Meteo 没有 {target_date.isoformat()} 的日出数据")
    sunrises = {
        day: _parse_local(stamp)
        for day, stamp in zip(dates, daily.get("sunrise") or [])
    }
    sunsets = {
        day: _parse_local(stamp)
        for day, stamp in zip(dates, daily.get("sunset") or [])
    }
    hourly_data = payload.get("hourly") or {}
    times = hourly_data.get("time") or []
    samples: list[CloudSeaSample] = []
    for i, stamp in enumerate(times):
        levels = []
        for hpa in PRESSURE_LEVELS:
            height = _optional_num(hourly_data.get(f"geopotential_height_{hpa}hPa"), i)
            if height is None:
                continue
            levels.append(
                PressureLevel(
                    hpa=hpa,
                    height_m=height,
                    temperature_c=_optional_num(hourly_data.get(f"temperature_{hpa}hPa"), i),
                    rh=_optional_num(hourly_data.get(f"relative_humidity_{hpa}hPa"), i),
                    cloud=_optional_num(hourly_data.get(f"cloud_cover_{hpa}hPa"), i),
                    wind_ms=_optional_num(hourly_data.get(f"wind_speed_{hpa}hPa"), i),
                )
            )
        samples.append(
            CloudSeaSample(
                time=stamp,
                temperature_2m=_optional_num(hourly_data.get("temperature_2m"), i),
                dew_point_2m=_optional_num(hourly_data.get("dew_point_2m"), i),
                humidity_2m=_optional_num(hourly_data.get("relative_humidity_2m"), i),
                cloud_low=_num(hourly_data.get("cloud_cover_low"), i),
                cloud_mid=_num(hourly_data.get("cloud_cover_mid"), i),
                cloud_high=_num(hourly_data.get("cloud_cover_high"), i),
                cloud_total=_num(hourly_data.get("cloud_cover"), i),
                visibility_m=_optional_num(hourly_data.get("visibility"), i),
                precip_mm=_optional_num(hourly_data.get("precipitation"), i),
                precip_probability=_optional_num(
                    hourly_data.get("precipitation_probability"), i
                ),
                wind_10m_ms=_optional_num(hourly_data.get("wind_speed_10m"), i),
                levels=tuple(levels),
            )
        )
    if not samples:
        raise ForecastError("Open-Meteo 没有云海所需的小时层结数据")
    return CloudSeaBundle(
        place=place,
        spot_name=spot_name,
        peak_m=peak_m,
        valley_m=valley_m,
        sunrises=sunrises,
        sunsets=sunsets,
        samples=samples,
    )


def cloudsea_sunrise_index(bundle: CloudSeaBundle, target_date: date) -> int:
    key = target_date.isoformat()
    if key not in bundle.sunrises:
        raise ForecastError(f"没有 {key} 的日出时刻")
    times = [item.time for item in bundle.samples]
    return _nearest_hour_index(times, bundle.sunrises[key])


def _num(series: list[Any] | None, index: int) -> float:
    value = _optional_num(series, index)
    return 0.0 if value is None else value


def _optional_num(series: list[Any] | None, index: int) -> float | None:
    if not series or index >= len(series):
        return None
    value = series[index]
    if value is None:
        return None
    return float(value)


def event_for_offset(day_offset: int) -> str:
    if day_offset <= 0:
        return EVENT_TODAY
    if day_offset == 1:
        return EVENT_TOMORROW
    raise ForecastError("SunsetBot 公开查询只覆盖今天和明天")


def local_today(timezone_name: str) -> date:
    # 标准库没有完整 IANA 时区表；对中国默认用 UTC+8，其它用系统本地日期。
    if timezone_name in {"Asia/Shanghai", "Asia/Chongqing", "Asia/Harbin", "Asia/Urumqi"}:
        return (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    return date.today()
