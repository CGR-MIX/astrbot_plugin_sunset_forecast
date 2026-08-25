#!/usr/bin/env python3
"""指定地点晚霞预报 CLI。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sunset_forecast.clients import ForecastError
from sunset_forecast.pipeline import forecast_cloud_sea, forecast_location
from sunset_forecast.places import DEFAULT_SUNSET_LOCATION
from sunset_forecast.spots import resolve_spot
from sunset_forecast.report import (
    CloudSeaDay,
    DayForecast,
    format_cloudsea_markdown,
    format_cloudsea_text,
    format_markdown,
    format_text,
)

CONFIG_PATH = ROOT / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {
            "location": DEFAULT_SUNSET_LOCATION,
            "cloud_sea_location": "新兴风车山",
            "days": 2,
            "daily_time": "14:30",
        }
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_history(kind: str, days: list, history_path: Path) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        "days": [asdict(item) for item in days],
    }
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def install_daily_task(location: str, time_of_day: str) -> str:
    config = load_config()
    config["location"] = location
    config["daily_time"] = time_of_day
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    python = sys.executable
    command = (
        f'cmd /c "cd /d {ROOT} && {python} predict.py --kind both --save '
        f'>> data\\daily.log 2>&1"'
    )
    create = [
        "schtasks",
        "/Create",
        "/TN",
        "SunsetForecastDaily",
        "/SC",
        "DAILY",
        "/ST",
        time_of_day,
        "/F",
        "/TR",
        command,
    ]
    completed = subprocess.run(
        create,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise ForecastError(f"创建计划任务失败：{output.strip()}")
    return output.strip() or "已创建计划任务 SunsetForecastDaily"


def parse_args(argv: list[str] | None, config: dict) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="查询指定地点的晚霞 / 云海评分与出现概率。"
    )
    parser.add_argument(
        "location_pos",
        nargs="?",
        default=None,
        help="地点，例如 广东肇庆端州区 / 肇庆 / 广州",
    )
    parser.add_argument("--location", "-l", default=None, help="地点（与位置参数二选一）")
    parser.add_argument(
        "--kind",
        choices=("sunset", "cloudsea", "both"),
        default=None,
        help="sunset=晚霞，cloudsea=云海，both=两个都跑。默认 sunset，可用 SUNSET_KIND",
    )
    parser.add_argument(
        "--cloud-sea-location",
        default=None,
        help="云海观景点，默认新兴风车山",
    )
    parser.add_argument("--lat", type=float, default=None, help="自定义观景纬度")
    parser.add_argument("--lng", type=float, default=None, help="自定义观景经度")
    parser.add_argument("--peak-m", type=float, default=None, help="观景海拔（米）")
    parser.add_argument("--valley-m", type=float, default=None, help="山谷海拔（米）")
    parser.add_argument("--days", type=int, default=None, help="预报天数，默认读配置或 SUNSET_DAYS")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--markdown", action="store_true", help="输出 Markdown")
    parser.add_argument("--save", action="store_true", help="追加写入 data/history.jsonl")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="同时写入 latest.txt / latest.md / latest.json",
    )
    parser.add_argument(
        "--github-summary",
        action="store_true",
        help="写入 GitHub Actions Job Summary（$GITHUB_STEP_SUMMARY）",
    )
    parser.add_argument(
        "--install-daily",
        action="store_true",
        help="用 Windows 计划任务在每天指定时间自动跑一次",
    )
    parser.add_argument(
        "--daily-time",
        default=str(config.get("daily_time") or "14:30"),
        help="安装每日任务时的本地时间，默认 14:30（中午场次更新后）",
    )
    return parser.parse_args(argv)


def _write_stem(output_dir: Path, stem: str, text: str, markdown: str, payload: object) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{stem}.txt").write_text(text, encoding="utf-8")
    (output_dir / f"{stem}.md").write_text(markdown, encoding="utf-8")
    (output_dir / f"{stem}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except OSError:
            pass
    config = load_config()
    args = parse_args(argv, config)
    location = (
        args.location
        or args.location_pos
        or os.environ.get("SUNSET_LOCATION")
        or config.get("location")
        or DEFAULT_SUNSET_LOCATION
    )
    cloud_sea_location = (
        args.cloud_sea_location
        or os.environ.get("CLOUDSEA_LOCATION")
        or config.get("cloud_sea_location")
        or "新兴风车山"
    )
    if args.days is None:
        env_days = os.environ.get("SUNSET_DAYS")
        args.days = int(env_days) if env_days else int(config.get("days") or 2)
    kind = args.kind or os.environ.get("SUNSET_KIND")
    if not kind:
        kind = "cloudsea" if resolve_spot(location) else "sunset"
    if args.install_daily:
        try:
            message = install_daily_task(location, args.daily_time)
        except ForecastError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return 1
        print(message)
        print(f"每天 {args.daily_time} 预测晚霞（{location}）和云海（{cloud_sea_location}）")
        return 0

    want_sunset = kind in {"sunset", "both"}
    want_cloudsea = kind in {"cloudsea", "both"}
    if kind == "cloudsea":
        cloud_sea_location = location if resolve_spot(location) else (args.location_pos or cloud_sea_location)
        if args.location or args.location_pos:
            cloud_sea_location = args.location or args.location_pos or cloud_sea_location

    sunset_days: list[DayForecast] = []
    cloudsea_days: list[CloudSeaDay] = []
    try:
        if want_sunset:
            sunset_days = forecast_location(location, days=args.days)
        if want_cloudsea:
            cloudsea_days = forecast_cloud_sea(
                cloud_sea_location,
                days=args.days,
                latitude=args.lat,
                longitude=args.lng,
                peak_m=args.peak_m,
                valley_m=args.valley_m,
            )
    except ForecastError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    text_parts: list[str] = []
    md_parts: list[str] = []
    payload: dict[str, object] = {}
    if sunset_days:
        text_parts.append(format_text(sunset_days))
        md_parts.append(format_markdown(sunset_days))
        payload["sunset"] = [asdict(item) for item in sunset_days]
    if cloudsea_days:
        text_parts.append(format_cloudsea_text(cloudsea_days))
        md_parts.append(format_cloudsea_markdown(cloudsea_days))
        payload["cloudsea"] = [asdict(item) for item in cloudsea_days]
    text = "\n".join(part.rstrip() for part in text_parts) + "\n"
    markdown = "\n".join(part.rstrip() for part in md_parts) + "\n"

    history = ROOT / (config.get("history_path") or "data/history.jsonl")
    if args.save:
        if sunset_days:
            save_history("sunset", sunset_days, history)
        if cloudsea_days:
            save_history("cloudsea", cloudsea_days, history)

    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_dir is not None:
        if not output_dir.is_absolute():
            output_dir = ROOT / output_dir
        if sunset_days:
            _write_stem(
                output_dir,
                "latest",
                format_text(sunset_days),
                format_markdown(sunset_days),
                payload.get("sunset"),
            )
        if cloudsea_days:
            _write_stem(
                output_dir,
                "cloudsea-latest",
                format_cloudsea_text(cloudsea_days),
                format_cloudsea_markdown(cloudsea_days),
                payload.get("cloudsea"),
            )
    if args.github_summary:
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if not summary_path:
            print("警告：未设置 GITHUB_STEP_SUMMARY，跳过 job summary。", file=sys.stderr)
        else:
            with open(summary_path, "a", encoding="utf-8") as handle:
                handle.write(markdown)
                if not markdown.endswith("\n"):
                    handle.write("\n")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.markdown:
        print(markdown, end="")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
