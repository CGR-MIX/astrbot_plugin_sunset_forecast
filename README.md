# 晚霞云海预报（AstrBot 插件）

查询指定城市的晚霞鲜艳度 / 出现概率，以及新兴风车山等点位的云海出现概率。

- 晚霞：SunsetBot GFS/EC + Open-Meteo 五因子
- 云海：Open-Meteo 气压层（山下成云 × 山顶出云）

## 用链接安装到 AstrBot

仓库地址（公开）：

```
https://github.com/CGR-MIX/astrbot_plugin_sunset_forecast
```

1. 打开 AstrBot WebUI → **插件管理**
2. 选择 **从 GitHub 安装** / **安装插件**
3. 粘贴上面的地址，安装后重启或重载插件

也可以在对话里（视你的 AstrBot 版本而定）：

```
/plugin install https://github.com/CGR-MIX/astrbot_plugin_sunset_forecast
```

## 指令

| 指令 | 说明 |
| --- | --- |
| `/晚霞 上海` | 今明两天晚霞 |
| `/火烧云 广州` | 同上 |
| `/云海` | 默认新兴风车山云海 |
| `/云海 风车山` | 指定观景点 |
| `/晚霞云海 广州` | 广州晚霞 + 默认云海点 |

插件配置里可改默认城市、默认观景点、预报天数。

## 本地命令行

```powershell
python predict.py 上海
python predict.py 新兴风车山
python predict.py --kind both
```

无第三方依赖，Python 3.10+ 即可。
