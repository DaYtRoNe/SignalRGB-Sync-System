# SignalRGB Sync System - installer
# Run via "Install.bat" (double-click). Safe to run again at any time: it
# re-installs packages, re-copies the effects and restarts the controller.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot        # ...\AlbumSpectrumBridge
$TaskName = "SignalRGBController"

function Step($n, $text) { Write-Host ""; Write-Host "[$n] $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "PROBLEM: $text" -ForegroundColor Red; Write-Host ""; exit 1 }

Write-Host "=============================================" -ForegroundColor Green
Write-Host "   SignalRGB Sync System - installer" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
Write-Host "Folder: $Root"

# ---------------------------------------------------------------- 1. Python
Step 1 "Looking for Python..."
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) {
    Fail "Python is not installed (or was installed without the 'py launcher').`n   Install Python from https://www.python.org/downloads/ - tick 'Add python.exe to PATH' - then run Install.bat again."
}
$exe = (& py -3 -c "import sys; print(sys.executable)").Trim()
$ver = (& py -3 -c "import sys; print('%d.%d.%d' % sys.version_info[:3])").Trim()
$pyw = Join-Path (Split-Path $exe) "pythonw.exe"
if (-not (Test-Path $pyw)) { Fail "pythonw.exe not found next to $exe" }
Write-Host "    Python $ver at $exe"
if ([version]$ver -lt [version]"3.12") { Fail "Python 3.12 or newer is needed (you have $ver). Install a newer Python and run again." }

# ---------------------------------------------------------------- 2. Packages
Step 2 "Installing the Python packages this needs (1-2 minutes)..."
& py -3 -m pip install --upgrade pip --quiet --disable-pip-version-check
& py -3 -m pip install --quiet --disable-pip-version-check -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) { Fail "Package installation failed. Check your internet connection and run Install.bat again." }
& py -3 -c "import PIL, winrt.windows.media.control, pycaw, psutil, mss, numpy, pyaudiowpatch, pystray" 2>$null
if ($LASTEXITCODE -ne 0) { Fail "Packages did not load correctly. Run Install.bat again; if it keeps failing, open an issue with the text of this window." }
Write-Host "    Packages OK"

# ---------------------------------------------------------------- 3. Effect files
Step 3 "Putting the effects (Album Pump Up Beats, Sync Lights Off, Sync Screen Dominant) into SignalRGB..."
# They go into SignalRGB's own program folder (like its built-in effects): the free tier
# loads at most 10 custom effects from Documents\WhirlwindFX\Effects, so that folder is
# unreliable. The controller re-copies them after every SignalRGB update.
$app = Get-ChildItem (Join-Path $env:LOCALAPPDATA "VortxEngine") -Directory -Filter "app-*" -ErrorAction SilentlyContinue |
    Sort-Object { [version]($_.Name.Substring(4)) } | Select-Object -Last 1
if ($app) {
    $effectsDir = Join-Path $app.FullName "Signal-x64\Effects\Dynamic"
    New-Item -ItemType Directory -Force -Path $effectsDir | Out-Null
    Get-ChildItem (Join-Path $Root "effect") -Filter *.html | Copy-Item -Destination $effectsDir -Force
    Write-Host "    Copied to $effectsDir"
    Write-Host "    (SignalRGB only scans this folder when it starts - restart SignalRGB after this installer finishes)" -ForegroundColor Yellow
} else {
    Write-Host "    SignalRGB program folder not found - is SignalRGB installed? The controller will copy the effects once it is." -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 4. Startup task
Step 4 "Making the controller start automatically when you log in..."
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue; Start-Sleep 2 }
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "rgb_controller\.py" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$action = New-ScheduledTaskAction -Execute $pyw -Argument '"rgb_controller.py"' -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$trigger.Delay = "PT10S"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force `
    -Description "SignalRGB Sync System: switches effects by what you are doing and sends album/screen colours (rgb_controller.py)" | Out-Null
Write-Host "    Task '$TaskName' registered"

# ---------------------------------------------------------------- 5. Start now
Step 5 "Starting the controller now..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep 8
$log = Join-Path $Root "controller.log"
if (Test-Path $log) {
    Write-Host "    --- controller.log ---" -ForegroundColor DarkGray
    Get-Content $log | Select-Object -Skip 6 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
}
$state = (Get-ScheduledTask -TaskName $TaskName).State
if ($state -ne "Running") { Fail "The controller did not stay running (state: $state). Open controller.log in this folder to see why." }

Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host "   Installed. The controller is running." -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next:"
Write-Host "  - Restart SignalRGB once (tray icon > Exit, then open it again) so it finds the new effects"
Write-Host "  - Settings > Audio > Audio Device = CABLE Input (VB-Audio Virtual Cable)"
Write-Host "  - Open the 'Album Pump Up Beats' effect once and set Color Style = Album"
Write-Host ""
if ((Get-Content $log -ErrorAction SilentlyContinue) -match "no playback device matching") {
    Write-Host "NOTE: VB-Audio Virtual Cable was not found. Music from browsers will not move the bars" -ForegroundColor Yellow
    Write-Host "      until you install it (Step 4 in the guide) and run Install.bat again." -ForegroundColor Yellow
    Write-Host ""
}
