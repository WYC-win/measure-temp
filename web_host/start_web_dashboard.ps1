$ErrorActionPreference = "Stop"

# 使用方法：
# 1) 在 PowerShell 中运行：
#    powershell -ExecutionPolicy Bypass -File .\web_host\start_web_dashboard.ps1

$pythonExe = "C:/Program Files/Python314/python.exe"
$projectDir = "c:/Users/WYC/Desktop/My code/measure temp"

Set-Location $projectDir

& $pythonExe web_host/web_dashboard.py