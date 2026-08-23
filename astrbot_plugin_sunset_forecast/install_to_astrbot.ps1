# 把本插件装进已有的 AstrBot data/plugins 目录。
# 用法：
#   .\install_to_astrbot.ps1 -AstrBotRoot "D:\AstrBot"

param(
    [Parameter(Mandatory = $true)]
    [string]$AstrBotRoot
)

$ErrorActionPreference = "Stop"
$PluginSrc = $PSScriptRoot
$RepoRoot = Split-Path $PluginSrc -Parent
$LibSrc = Join-Path $RepoRoot "sunset_forecast"
$PluginDst = Join-Path $AstrBotRoot "data\plugins\astrbot_plugin_sunset_forecast"

if (-not (Test-Path $LibSrc)) {
    throw "找不到预报库：$LibSrc"
}

New-Item -ItemType Directory -Force -Path $PluginDst | Out-Null
Copy-Item -Force (Join-Path $PluginSrc "main.py") $PluginDst
Copy-Item -Force (Join-Path $PluginSrc "metadata.yaml") $PluginDst
Copy-Item -Force (Join-Path $PluginSrc "_conf_schema.json") $PluginDst
Copy-Item -Force (Join-Path $PluginSrc "requirements.txt") $PluginDst

$LibDst = Join-Path $PluginDst "sunset_forecast"
if (Test-Path $LibDst) {
    cmd /c "rmdir `"$LibDst`"" | Out-Null
    if (Test-Path $LibDst) {
        Remove-Item -Recurse -Force $LibDst
    }
}

$junction = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "mklink /J `"$LibDst`" `"$LibSrc`"" -Wait -PassThru -WindowStyle Hidden
if ($junction.ExitCode -ne 0) {
    Copy-Item -Recurse -Force $LibSrc $LibDst
    Write-Host "无法创建目录联接，已改为复制 sunset_forecast。"
} else {
    Write-Host "已联接预报库 -> $LibDst"
}

Write-Host "插件已放到 $PluginDst"
Write-Host "请重启 AstrBot，然后在对话里发送 /晚霞 上海 或 /云海"
