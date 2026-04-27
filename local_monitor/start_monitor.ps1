$ErrorActionPreference = "Stop"

# 使用方法：
# 1) 在 PowerShell 中运行：
#    powershell -ExecutionPolicy Bypass -File .\local_monitor\start_monitor.ps1

$pythonExe = "C:/Program Files/Python314/python.exe"
$projectDir = "c:/Users/WYC/Desktop/My code/measure temp"

Set-Location $projectDir

& $pythonExe local_monitor/monitor.py