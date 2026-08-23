"""中国城市坐标。优先用内置全国地级/区县表，不依赖 Open-Meteo 会不会写「市」。"""

from __future__ import annotations

import json
from pathlib import Path

from .prefectures import PREFECTURES

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
    "肇庆": (23.0472, 112.4653, "广东", 4114000),
    "佛山": (23.0218, 113.1219, "广东", 9498000),
    "云浮": (22.9150, 112.0445, "广东", 2383000),
    "清远": (23.6820, 113.0560, "广东", 3969000),
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


def _read_city_json() -> dict[str, list]:
    here = Path(__file__).resolve().parent
    candidates: list[Path] = [
        here / "data" / "china_cities.json",
        here.parent / "sunset_forecast" / "data" / "china_cities.json",
    ]
    try:
        from importlib.resources import files

        resource = files("sunset_forecast").joinpath("data/china_cities.json")
        if hasattr(resource, "read_text"):
            return json.loads(resource.read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    for path in candidates:
        try:
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def _load_cities() -> dict[str, list]:
    global _CITIES
    if _CITIES is not None:
        return _CITIES
    loaded: dict[str, list] = {name: list(row) for name, row in PREFECTURES.items()}
    loaded.update(_read_city_json())
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


def normalize_query(location: str) -> str:
    """去掉指令词、@、CQ 码，留下城市名。"""
    import re

    text = location or ""
    text = re.sub(r"\[CQ:[^\]]+\]", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"@\S+", " ", text)
    for token in ("/", "／", "#", ",", "，", "。", "·", "-", "_"):
        text = text.replace(token, " ")
    for prefix in (
        "晚霞云海",
        "晚霞诊断",
        "火烧云",
        "晚霞",
        "云海",
        "sunset",
        "cloudsea",
        "查询",
        "查一下",
        "诊断",
    ):
        text = text.replace(prefix, " ")
    return "".join(text.split())


def lookup_keys(location: str) -> list[str]:
    compact = normalize_query(location)
    raw = location.strip().replace(" ", "").replace("　", "").replace("-", "").replace("·", "")
    keys: list[str] = []
    for compact_item in (compact, raw, location.strip()):
        keys.extend(geocode_query_variants(compact_item))
        keys.append(city_key(compact_item))
        for prov in PROVINCES:
            if compact_item.startswith(prov) and len(compact_item) > len(prov):
                rest = compact_item[len(prov) :]
                keys.extend(geocode_query_variants(rest))
                keys.append(prov + city_key(rest))
    return _unique(keys)


def _longest_table_hit(text: str, cities: dict[str, list]) -> str | None:
    if not text:
        return None
    best = ""
    pool = set(PREFECTURES) | set(BUILTIN_CITIES) | set(cities)
    for key in pool:
        if 2 <= len(key) <= 6 and key in text and len(key) > len(best):
            best = key
    return best or None


def lookup_china_city(location: str) -> tuple[float, float, str, str] | None:
    """返回 lat, lng, admin1, 显示名。"""
    cities = _load_cities()
    for key in lookup_keys(location):
        row = cities.get(key)
        if row is None:
            continue
        lat, lng, admin1 = float(row[0]), float(row[1]), str(row[2])
        return lat, lng, admin1, city_key(key) or key
    compact = normalize_query(location)
    hit = _longest_table_hit(compact, cities) or _longest_table_hit(
        location.replace(" ", ""), cities
    )
    if hit is None:
        return None
    row = cities.get(hit)
    if row is None:
        row = PREFECTURES.get(hit)
    if row is None and hit in BUILTIN_CITIES:
        lat0, lng0, admin0, _pop = BUILTIN_CITIES[hit]
        row = [lat0, lng0, admin0]
    if row is None:
        return None
    lat, lng, admin1 = float(row[0]), float(row[1]), str(row[2])
    return lat, lng, admin1, city_key(hit) or hit
