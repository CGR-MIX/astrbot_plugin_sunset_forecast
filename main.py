"""AstrBot 插件：把本仓库的晚霞 / 云海预报接到 QQ 等对话里。"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent


def _ensure_lib_on_path() -> None:
    candidates = [
        PLUGIN_DIR,
        PLUGIN_DIR.parent,
        Path(PLUGIN_DIR / "vendor"),
    ]
    env_root = os.environ.get("SUNSET_FORECAST_ROOT")
    if env_root:
        candidates.insert(0, Path(env_root))
    for root in candidates:
        if (root / "sunset_forecast" / "pipeline.py").exists():
            resolved = str(root)
            if resolved in sys.path:
                sys.path.remove(resolved)
            sys.path.insert(0, resolved)
            for name in list(sys.modules):
                if name == "sunset_forecast" or name.startswith("sunset_forecast."):
                    del sys.modules[name]
            return
    raise RuntimeError(
        "找不到 sunset_forecast 包。请把仓库里的 sunset_forecast 目录放到本插件旁，"
        "或设置环境变量 SUNSET_FORECAST_ROOT。"
    )


_ensure_lib_on_path()

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from sunset_forecast.clients import ForecastError, geocode
from sunset_forecast.pipeline import forecast_cloud_sea, forecast_location
from sunset_forecast.places import _load_cities, lookup_china_city
from sunset_forecast.report import format_cloudsea_chat, format_sunset_chat
from sunset_forecast.spots import resolve_spot

COMMAND_PREFIXES = (
    "晚霞云海",
    "晚霞诊断",
    "火烧云",
    "晚霞",
    "云海",
    "sunset",
    "cloudsea",
)
QUERY_TIMEOUT_SEC = 25


def _cfg(config, key: str, default):
    if config is None:
        return default
    try:
        value = config.get(key, default)
    except Exception:
        return default
    return default if value is None or value == "" else value


def _event_text(event: AstrMessageEvent) -> str:
    chunks: list[str] = []
    if hasattr(event, "get_message_str"):
        chunks.append(str(event.get_message_str() or ""))
    if hasattr(event, "message_str"):
        chunks.append(str(event.message_str or ""))
    obj = getattr(event, "message_obj", None)
    if obj is not None:
        chunks.append(str(getattr(obj, "message_str", "") or ""))
        raw = getattr(obj, "message", None)
        if isinstance(raw, str):
            chunks.append(raw)
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    chunks.append(item)
                elif isinstance(item, dict):
                    chunks.append(str(item.get("text") or item.get("content") or ""))
                else:
                    chunks.append(str(getattr(item, "text", "") or ""))
    return " ".join(chunk for chunk in chunks if chunk).strip()


def _rest_arg(event: AstrMessageEvent) -> str:
    text = _event_text(event)
    if text.startswith("/"):
        text = text[1:].strip()
    for prefix in COMMAND_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


async def _run(func, *args, **kwargs):
    return await asyncio.wait_for(
        asyncio.to_thread(func, *args, **kwargs),
        timeout=QUERY_TIMEOUT_SEC,
    )


@register("sunset_forecast", "ChanGR", "晚霞与云海预报", "1.0.5")
class SunsetForecastPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config
        n_cities = len(_load_cities())
        logger.info("插件 [sunset_forecast] v1.0.5 已加载，城市表 %s 条。", n_cities)

    def _days(self) -> int:
        try:
            days = int(_cfg(self.config, "days", 2))
        except (TypeError, ValueError):
            days = 2
        return min(max(days, 1), 2)

    def _city(self, event: AstrMessageEvent, extra: str = "") -> str:
        raw = (extra or "").strip() or _rest_arg(event)
        hit = lookup_china_city(raw) if raw else None
        if hit is not None:
            return hit[3]
        cleaned = raw.strip() if raw else ""
        return cleaned or str(_cfg(self.config, "default_city", "上海"))

    def _spot(self, event: AstrMessageEvent, extra: str = "") -> str:
        return (
            (extra or "").strip()
            or _rest_arg(event)
            or str(_cfg(self.config, "default_cloudsea", "新兴风车山"))
        )

    @filter.command("晚霞")
    async def cmd_sunset(self, event: AstrMessageEvent, city: str = ""):
        """查询今晚/明天晚霞评分和概率。例：/晚霞 上海"""
        location = self._city(event, city)
        if resolve_spot(location):
            yield event.plain_result(
                f"「{location}」是云海观景点。查云海请用 /云海 {location}，晚霞请写城市，例如 /晚霞 广州"
            )
            return
        try:
            days = await _run(forecast_location, location, days=self._days())
            yield event.plain_result(format_sunset_chat(days))
        except asyncio.TimeoutError:
            yield event.plain_result("晚霞查询超时，请稍后再试。")
        except ForecastError as exc:
            yield event.plain_result(f"晚霞查询失败：{exc}")
        except Exception:
            logger.exception("晚霞查询异常")
            yield event.plain_result("晚霞查询出错了，请稍后再试。")

    @filter.command("晚霞诊断")
    async def cmd_diag(self, event: AstrMessageEvent, city: str = ""):
        """检查插件版本、城市表，以及某个地名能不能定位。例：/晚霞诊断 肇庆"""
        raw = (city or "").strip() or _rest_arg(event) or "肇庆"
        cities = _load_cities()
        hit = lookup_china_city(raw)
        try:
            place = geocode(raw)
            geo_line = f"{place.admin1}/{place.name} {place.latitude:.4f},{place.longitude:.4f}"
        except Exception as exc:
            geo_line = f"失败：{exc}"
        yield event.plain_result(
            "晚霞插件诊断 v1.0.5\n"
            f"城市表 {len(cities)} 条\n"
            f"原始输入 {raw!r}\n"
            f"表内命中 {hit}\n"
            f"定位结果 {geo_line}"
        )

    @filter.command("火烧云")
    async def cmd_huoshaoyun(self, event: AstrMessageEvent, city: str = ""):
        """查询今晚/明天晚霞评分和概率。例：/火烧云 广州"""
        async for item in self.cmd_sunset(event, city):
            yield item

    @filter.command("云海")
    async def cmd_cloudsea(self, event: AstrMessageEvent, spot: str = ""):
        """查询云海出现概率。默认新兴风车山。例：/云海  或  /云海 风车山"""
        spot = self._spot(event, spot)
        try:
            days = await _run(forecast_cloud_sea, spot, days=self._days())
            yield event.plain_result(format_cloudsea_chat(days))
        except asyncio.TimeoutError:
            yield event.plain_result("云海查询超时，请稍后再试。")
        except ForecastError as exc:
            yield event.plain_result(f"云海查询失败：{exc}")
        except Exception:
            logger.exception("云海查询异常")
            yield event.plain_result("云海查询出错了，请稍后再试。")

    @filter.command("晚霞云海")
    async def cmd_both(self, event: AstrMessageEvent, city: str = ""):
        """同时查晚霞和默认观景点云海。例：/晚霞云海 广州"""
        city = self._city(event, city)
        spot = str(_cfg(self.config, "default_cloudsea", "新兴风车山"))
        if resolve_spot(city):
            spot = city
            city = str(_cfg(self.config, "default_city", "上海"))
        try:
            sunset_days, sea_days = await asyncio.wait_for(
                asyncio.gather(
                    _run(forecast_location, city, days=self._days()),
                    _run(forecast_cloud_sea, spot, days=self._days()),
                ),
                timeout=QUERY_TIMEOUT_SEC,
            )
            yield event.plain_result(
                format_sunset_chat(sunset_days) + "\n\n" + format_cloudsea_chat(sea_days)
            )
        except asyncio.TimeoutError:
            yield event.plain_result("查询超时，请稍后再试。")
        except ForecastError as exc:
            yield event.plain_result(f"查询失败：{exc}")
        except Exception:
            logger.exception("晚霞云海查询异常")
            yield event.plain_result("查询出错了，请稍后再试。")

    @filter.llm_tool(name="forecast_sunset")
    async def tool_sunset(self, event: AstrMessageEvent, location: str) -> str:
        """查询指定城市今晚和明天的晚霞鲜艳度、AOD 和出现概率。
        Args:
            location(string): 城市名，例如上海、广州、杭州
        """
        try:
            days = await _run(forecast_location, location, days=self._days())
            return format_sunset_chat(days)
        except Exception as exc:
            return f"晚霞查询失败：{exc}"

    @filter.llm_tool(name="forecast_cloud_sea")
    async def tool_cloudsea(self, event: AstrMessageEvent, spot: str) -> str:
        """查询指定观景点的云海出现概率，默认新兴风车山。
        Args:
            spot(string): 观景点名称，例如新兴风车山、风车山。未知山头需要先录入海拔。
        """
        name = (spot or "").strip() or str(_cfg(self.config, "default_cloudsea", "新兴风车山"))
        try:
            days = await _run(forecast_cloud_sea, name, days=self._days())
            return format_cloudsea_chat(days)
        except Exception as exc:
            return f"云海查询失败：{exc}"
