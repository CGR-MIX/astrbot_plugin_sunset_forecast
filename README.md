# 晚霞云海预报（AstrBot 插件）

查询指定城市的晚霞鲜艳度 / 出现概率，以及新兴风车山等点位的云海出现概率。

- 晚霞：SunsetBot GFS/EC + Open-Meteo 五因子
- 云海：Open-Meteo 气压层（山下成云 × 山顶出云）

当前版本：**v1.0.6**

## 用链接安装到 AstrBot

```
https://github.com/CGR-MIX/astrbot_plugin_sunset_forecast
```

1. 先在插件管理里 **卸载旧的「晚霞云海预报」**
2. 重启 AstrBot
3. 从 GitHub 安装，粘贴上面的地址（不要填子目录）
4. 装完发 `/晚霞诊断 肇庆`，第一行必须是 `v1.0.6`

AstrBot 的「检查更新」读取 GitHub **Release**，不是每一次 commit。这个仓库的 Release 是 `v1.0.6`。

## 指令

| 指令 | 说明 |
| --- | --- |
| `/晚霞 上海` | 今明两天晚霞 |
| `/晚霞 肇庆` | 同上 |
| `/晚霞诊断 肇庆` | 看版本和城市表是否命中 |
| `/火烧云 广州` | 同晚霞 |
| `/云海` | 默认新兴风车山云海 |
| `/晚霞云海 广州` | 广州晚霞 + 默认云海点 |

## 本地命令行

```powershell
python predict.py 上海
python predict.py 肇庆
python predict.py 新兴风车山
```
