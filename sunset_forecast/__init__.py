"""指定地点晚霞 / 云海评分、概率预测与每日预报。"""

from .pipeline import forecast_cloud_sea, forecast_location

__all__ = ["forecast_location", "forecast_cloud_sea"]
__version__ = "1.1.0"
