"""中国城市坐标。优先用内置全国地级/区县表，不依赖 Open-Meteo 会不会写「市」。"""

from __future__ import annotations

import json
from pathlib import Path

# 少量手写覆盖，优先级高于数据包。
BUILTIN_CITIES: dict[str, tuple[float, float, str, int]] = {
    "北京": (39.9042, 116.4074, "北京", 21540000),
    "上海": (31.2304, 121.4737, "上海", 24870000),
    "天津": (39.0842, 117.2009, "天津", 13640000),
    "重庆": (29.5630, 106.5516, "重庆", 32050000),
    "香港": (22.3193, 114.1694, "香港", 7500000),
    "澳门": (22.1987, 113.5439, "澳门", 680000),
    "广州": (23.1291, 113.2644, "广东", 16090000),
    "深圳": (22.5431, 114.0579, "广东", 17560000),
    "杭州": (30.2741, 120.1551, "浙江", 11936000),
}

PROVINCES: tuple[str, ...] = (
    "黑龙江",
    "内蒙古",
    "新疆",
    "西藏",
    "广西",
    "宁夏",
    "香港",
    "澳门",
    "台湾",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "北京",
    "天津",
    "上海",
    "重庆",
)

_CITIES: dict[str, list] | None = None


def city_key(name: str) -> str:
    text = name.strip()
    for suffix in ("特别行政区", "地区", "自治州", "自治县", "林区", "市", "县", "区", "旗", "盟"):
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)]
    return text


def geocode_query_variants(location: str) -> list[str]:
    name = location.strip()
    variants = [name]
    key = city_key(name)
    if key and key not in variants:
        variants.append(key)
    if key:
        for extra in (key + "市", key + "县", key + "区"):
            if extra not in variants:
                variants.append(extra)
    return variants


def _load_cities() -> dict[str, list]:
    global _CITIES
    if _CITIES is not None:
        return _CITIES
    path = Path(__file__).resolve().parent / "data" / "china_cities.json"
    loaded: dict[str, list] = {}
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
    for name, (lat, lng, admin1, _pop) in BUILTIN_CITIES.items():
        loaded[name] = [lat, lng, admin1]
    _CITIES = loaded
    return loaded


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def lookup_keys(location: str) -> list[str]:
    compact = location.strip().replace(" ", "").replace("　", "").replace("-", "").replace("·", "")
    keys = geocode_query_variants(compact)
    keys.append(city_key(compact))
    for prov in PROVINCES:
        if compact.startswith(prov) and len(compact) > len(prov):
            rest = compact[len(prov) :]
            keys.extend(geocode_query_variants(rest))
            keys.append(prov + city_key(rest))
    return _unique(keys)


def lookup_china_city(location: str) -> tuple[float, float, str, str] | None:
    """返回 lat, lng, admin1, 显示名。"""
    cities = _load_cities()
    for key in lookup_keys(location):
        row = cities.get(key)
        if row is None:
            continue
        lat, lng, admin1 = float(row[0]), float(row[1]), str(row[2])
        return lat, lng, admin1, city_key(key) or key
    return None
