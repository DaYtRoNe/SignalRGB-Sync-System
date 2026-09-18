# SignalRGB Sync System - uninstaller. Run via "Uninstall.bat".
$Root = Split-Path -Parent $PSScriptRoot
$TaskName = "SignalRGBController"

Write-Host "Stopping and removing the startup task..."
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Write-Host "Closing any running controller / AIMP helper..."
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "rgb_controller\.py" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-Process AimpSmtc -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

$effectsDir = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "WhirlwindFX\Effects"
$effects = @("Album Pump Up Beats.html", "Lights Off.html") | ForEach-Object { Join-Path $effectsDir $_ } | Where-Object { Test-Path $_ }
if ($effects) {
    $answer = Read-Host "Also remove the 'Album Pump Up Beats' and 'Lights Off' effects from SignalRGB? (y/n)"
    if ($answer -match "^[yY]") { $effects | Remove-Item -Force; Write-Host "Effects removed." }
}

Write-Host ""
Write-Host "Done. The automation is off and will not start at login any more."
Write-Host "You can delete the folder $Root if you no longer want the files."
Write-Host "(VB-Audio Virtual Cable and Python were left installed - remove them from Windows 'Installed apps' if you want.)"
Write-Host ""
