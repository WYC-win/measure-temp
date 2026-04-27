$ErrorActionPreference = "Stop"

# 使用方法：
# powershell -ExecutionPolicy Bypass -File .\web_host\start_csv_sync.ps1

$pythonExe = "c:/Users/WYC/Desktop/My code/measure temp/.venv/Scripts/python.exe"
$projectDir = "c:/Users/WYC/Desktop/My code/measure temp"

Set-Location $projectDir

$securePwd = Read-Host "请输入云服务器 root 密码" -AsSecureString
$plainPwd = [System.Net.NetworkCredential]::new("", $securePwd).Password
$env:TEMP_SYNC_PASSWORD = $plainPwd

& $pythonExe web_host/sync_csv_to_server.py `
  --host 39.105.108.171 `
  --user root `
  --remote-dir /opt/temperature-web `
  --interval 2.0
