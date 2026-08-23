# 把本仓库作为 AstrBot 插件装进 data/plugins。
# 用法：.\install_to_astrbot.ps1 -AstrBotRoot "D:\AstrBot"

param(
    [Parameter(Mandatory = $true)]
    [string]$AstrBotRoot
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$LibSrc = Join-Path $RepoRoot "sunset_forecast"
$PluginDst = Join-Path $AstrBotRoot "data\plugins\astrbot_plugin_sunset_forecast"

if (-not (Test-Path (Join-Path $RepoRoot "main.py"))) {
    throw "仓库根目录缺少 main.py：$RepoRoot"
}
if (-not (Test-Path $LibSrc)) {
    throw "找不到预报库：$LibSrc"
}

New-Item -ItemType Directory -Force -Path $PluginDst | Out-Null
Copy-Item -Force (Join-Path $RepoRoot "main.py") $PluginDst
Copy-Item -Force (Join-Path $RepoRoot "metadata.yaml") $PluginDst
Copy-Item -Force (Join-Path $RepoRoot "_conf_schema.json") $PluginDst
Copy-Item -Force (Join-Path $RepoRoot "requirements.txt") $PluginDst

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
Write-Host "请重启 AstrBot，发送 /晚霞诊断 肇庆 确认版本是 v1.0.6"
