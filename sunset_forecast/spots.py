"""观景点位。云海必须用真实观景海拔，不能信网格 DEM（风车山会被标成两百多米）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewSpot:
    key: str
    name: str
    aliases: tuple[str, ...]
    latitude: float
    longitude: float
    peak_m: float
    valley_m: float
    timezone: str
    admin1: str
    note: str
    sunsetbot_city: str | None = None


DEFAULT_CLOUDSEA_LOCATION = "云浮风车山"

# 云浮市新兴县水源山 18 号风车。坐标来自公开徒步轨迹；海拔来自地方志/攻略。
XINXING_FENGCHESHAN = ViewSpot(
    key="xinxing-fengcheshan",
    name="云浮风车山",
    aliases=(
        "云浮风车山",
        "新兴风车山",
        "风车山",
        "水源山",
        "18号风车",
        "新兴水源山",
        "天露山风电场",
        "新兴县风车山",
        "云浮新兴风车山",
    ),
    latitude=22.7289,
    longitude=112.0587,
    peak_m=1137.0,
    valley_m=80.0,
    timezone="Asia/Shanghai",
    admin1="广东",
    note="云浮市新兴县水源山 18 号风车（1137 m），俯瞰山谷/开平大沙水库方向。云海多在日出前后。",
    sunsetbot_city="云浮",
)

SPOTS: tuple[ViewSpot, ...] = (XINXING_FENGCHESHAN,)


def normalize_spot_name(name: str) -> str:
    text = name.strip().lower().replace(" ", "").replace("　", "")
    for token in ("镇", "县", "市", "区"):
        if text.endswith(token) and len(text) > len(token) + 1:
            text = text[: -len(token)]
    return text


def resolve_spot(name: str | None) -> ViewSpot | None:
    if not name:
        return None
    needle = normalize_spot_name(name)
    for spot in SPOTS:
        candidates = (spot.name, spot.key, *spot.aliases)
        if any(normalize_spot_name(item) == needle for item in candidates):
            return spot
        if any(needle in normalize_spot_name(item) for item in candidates):
            return spot
    return None
