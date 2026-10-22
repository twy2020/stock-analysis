param(
  [ValidateSet('stock-analysis', 'stock-analysis-market-relay')]
  [string]$AppId = 'stock-analysis',
  [ValidateSet('select', 'start', 'stop', 'restart', 'logs', 'open', 'close-window', 'reopen')]
  [string]$Action = 'select'
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class StockHubDesktop {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out Rect rect);
  [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
}
'@
$executable = 'F:\my_projects\collabflow\service-hub\release\win-unpacked\Service Hub.exe'
$identity = Invoke-RestMethod http://127.0.0.1:18765/api/identity
if ($identity.service -ne 'service-hub' -or $identity.version -lt 2 -or
    $identity.registryPath -ne (Join-Path $env:USERPROFILE '.service-hub/apps.json')) {
  throw 'Unexpected Service Hub identity or registry'
}
$apps = Invoke-RestMethod http://127.0.0.1:18765/api/apps
$entry = $apps | Where-Object id -eq $AppId
if (-not $entry) { throw 'Application is not registered' }
if ($Action -eq 'reopen') {
  Start-Process -FilePath $executable -WindowStyle Hidden
  Start-Sleep -Milliseconds 1200
}
$process = Get-Process | Where-Object { $_.Path -eq $executable -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $process) { throw 'Official Service Hub window not found' }
$handle = $process.MainWindowHandle
[void][StockHubDesktop]::ShowWindow($handle, 9)
[void][StockHubDesktop]::SetForegroundWindow($handle)
$root = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
function Find-Element([string]$value, [bool]$byId = $false) {
  $property = if ($byId) { [System.Windows.Automation.AutomationElement]::AutomationIdProperty }
              else { [System.Windows.Automation.AutomationElement]::NameProperty }
  $condition = [System.Windows.Automation.PropertyCondition]::new($property, $value)
  $item = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
  if (-not $item) { throw "Desktop element not found: $value" }
  return $item
}
function Invoke-Element([string]$value, [bool]$byId = $false) {
  $element = Find-Element $value $byId
  $pattern = $element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
  $pattern.Invoke()
}
if ($Action -eq 'close-window') {
  $root.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern).Close()
  Write-Output 'Official Electron window closed to tray'
  exit
}
try {
  $detail = Find-Element 'detail' $true
  $close = $detail.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.PropertyCondition]::new(
      [System.Windows.Automation.AutomationElement]::NameProperty, '关闭'))
  $close.SetFocus()
  $close.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
  Start-Sleep -Milliseconds 200
} catch { }
$search = Find-Element 'search' $true
$search.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($entry.name)
Start-Sleep -Milliseconds 600
if ($Action -in @('stop', 'restart') -and $AppId -eq 'stock-analysis') {
  $code = @'
import sqlite3
c=sqlite3.connect('file:/data/stock-core.sqlite3?mode=ro',uri=True)
print(c.execute("SELECT count(*) FROM runs WHERE status IN ('QUEUED','RUNNING')").fetchone()[0])
'@
  $count = $code | docker exec -i stock-analysis-core-1 python -
  if ($LASTEXITCODE -ne 0 -or $count.Trim() -ne '0') { throw 'Active-run safety check failed' }
  $code = @'
import sqlite3
c=sqlite3.connect('file:/data/stock-chat.db?mode=ro',uri=True)
tables={r[0] for r in c.execute("select name from sqlite_master where type='table'")}
print(sum(c.execute("select count(*) from "+t+" where status in ('QUEUED','RUNNING')").fetchone()[0]
          for t in ('chat_runs','audit_records') if t in tables))
'@
  $count = $code | docker exec -i stock-analysis-backend-1 python -
  if ($LASTEXITCODE -ne 0 -or $count.Trim() -ne '0') { throw 'Active SaaS task safety check failed' }
}
switch ($Action) {
  'start' { Invoke-Element '启动' }
  'stop' { Invoke-Element '停止'; Start-Sleep -Milliseconds 200; Invoke-Element 'confirm-yes' $true }
  'restart' { Invoke-Element '重启'; Start-Sleep -Milliseconds 200; Invoke-Element 'confirm-yes' $true }
  'logs' { Invoke-Element '应用详情'; Start-Sleep -Milliseconds 200; Invoke-Element '日志' }
  'open' { Invoke-Element '打开应用' }
}
Write-Output "Official Electron UI: $AppId / $Action"
if ($Action -in @('start', 'stop', 'restart')) {
  $deadline = (Get-Date).AddSeconds(90)
  do {
    Start-Sleep -Milliseconds 800
    $status = Invoke-RestMethod http://127.0.0.1:18765/api/status
    $job = $status.jobs | Where-Object { $_.appId -eq $AppId -and $_.action -eq $Action } | Select-Object -Last 1
    if ($job -and $job.state -ne 'running') {
      if ($job.state -ne 'success') { throw "Desktop action failed: $($job.output)" }
      Write-Output "Job $($job.id): $($job.state)"
      break
    }
  } while ((Get-Date) -lt $deadline)
  if (-not $job -or $job.state -eq 'running') { throw 'Desktop action timed out' }
}
if ($Action -eq 'logs') {
  $marker = if ($AppId -eq 'stock-analysis-market-relay') { 'Stock market relay listening' }
            else { 'Booting worker|Starting gunicorn|Serving Flask app|Running on' }
  $deadline = (Get-Date).AddSeconds(20)
  do {
    Start-Sleep -Milliseconds 500
    $detail = Find-Element 'detail' $true
    $logElement = $detail.FindAll([System.Windows.Automation.TreeScope]::Descendants,
      [System.Windows.Automation.Condition]::TrueCondition) |
      Where-Object { $_.Current.Name -match $marker } | Select-Object -First 1
  } while (-not $logElement -and (Get-Date) -lt $deadline)
  $found = [bool]$logElement
  Write-Output "Expected application log rendered: $found"
  if (-not $found) { throw 'Expected application logs not rendered in Electron' }
  try { $logElement.GetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern).ScrollIntoView() } catch { }
}
if ($Action -ne 'open') {
  Add-Type -AssemblyName System.Drawing
  $directory = Join-Path (Split-Path -Parent $PSScriptRoot) 'artifacts/verification/service-hub'
  [void](New-Item -ItemType Directory -Path $directory -Force)
  $rect = [StockHubDesktop+Rect]::new()
  [void][StockHubDesktop]::GetWindowRect($handle, [ref]$rect)
  $bitmap = [System.Drawing.Bitmap]::new($rect.Right - $rect.Left, $rect.Bottom - $rect.Top)
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  try {
    $hdc = $graphics.GetHdc()
    try { [void][StockHubDesktop]::PrintWindow($handle, $hdc, 2) }
    finally { $graphics.ReleaseHdc($hdc) }
    $bitmap.Save((Join-Path $directory "$AppId-$Action.png"))
  } finally { $graphics.Dispose(); $bitmap.Dispose() }
}
