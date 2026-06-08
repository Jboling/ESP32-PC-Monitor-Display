# Run the PC stats agent and send metrics to the ESP32 display.
# USB serial: auto-detects COM port (Espressif USB VID 303A).
# WiFi: discovers the display via mDNS using .env in the project root.

param(
    [ValidateSet("serial", "wifi", "auto")]
    [string]$Transport = "serial",
    [string]$Port,
    [string]$WifiHost,
    [int]$WifiPort = 0,
    [int]$Baud = 115200,
    [double]$Interval = 1.0,
    [int]$GpuIndex = 0
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Get-Esp32ComPortsFromPio {
    $pio = Get-Command pio -ErrorAction SilentlyContinue
    if (-not $pio) {
        return @()
    }

    $output = (pio device list 2>&1 | Out-String)
    $ports = @()

    $matches = [regex]::Matches($output, '(COM\d+)\r?\n----\r?\n((?:.*\r?\n)*?)(?=COM\d+\r?\n----|\z)')
    foreach ($match in $matches) {
        $com = $match.Groups[1].Value
        $details = $match.Groups[2].Value

        $isEspressif = $details -match 'VID:PID=303A:' -or
                       $details -match 'Espressif' -or
                       $details -match 'USB JTAG/serial'

        if ($isEspressif) {
            $ports += [PSCustomObject]@{
                Port = $com
                Details = ($details -replace '\s+', ' ').Trim()
            }
        }
    }

    return $ports
}

function Get-Esp32ComPortsFromPyserial {
    param([string]$PythonExe)

    $script = @'
import json
import serial.tools.list_ports

ports = []
for p in serial.tools.list_ports.comports():
    if p.vid == 0x303A:
        desc = p.description or ""
        ports.append({"Port": p.device, "Details": desc})

print(json.dumps(ports))
'@

    $json = & $PythonExe -c $script 2>$null
    if (-not $json) {
        return @()
    }

    return @($json | ConvertFrom-Json) | ForEach-Object {
        [PSCustomObject]@{
            Port = $_.Port
            Details = $_.Details
        }
    }
}

function Get-Esp32ComPorts {
    $ports = @(Get-Esp32ComPortsFromPio)
    if ($ports.Count -gt 0) {
        return $ports
    }

    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return @(Get-Esp32ComPortsFromPyserial -PythonExe $venvPython)
    }

    return @()
}

function Select-ComPort {
    param([System.Collections.IEnumerable]$Candidates)

    if ($Candidates.Count -eq 0) {
        Write-Host ""
        Write-Host "No ESP32 COM port found." -ForegroundColor Red
        Write-Host "  - Plug in the board via USB"
        Write-Host "  - Close serial monitor / other apps using the port"
        Write-Host "  - Run: pio device list"
        exit 1
    }

    if ($Candidates.Count -eq 1) {
        return $Candidates[0].Port
    }

    Write-Host "Multiple ESP32 ports found:" -ForegroundColor Yellow
    for ($i = 0; $i -lt $Candidates.Count; $i++) {
        $item = $Candidates[$i]
        $detail = if ($item.Details) { " - $($item.Details)" } else { "" }
        Write-Host ("  [{0}] {1}{2}" -f ($i + 1), $item.Port, $detail)
    }

    $choice = Read-Host "Select port number"
    $index = [int]$choice - 1
    if ($index -lt 0 -or $index -ge $Candidates.Count) {
        Write-Error "Invalid selection."
    }
    return $Candidates[$index].Port
}

function Ensure-Venv {
    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "Creating virtual environment..." -ForegroundColor Cyan
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to create virtual environment."
        }
    }

    $requirements = Join-Path $PSScriptRoot "requirements.txt"
    $stamp = Join-Path $PSScriptRoot ".venv\.deps-installed"
    if (-not (Test-Path $stamp) -or (Get-Item $requirements).LastWriteTime -gt (Get-Item $stamp).LastWriteTime) {
        Write-Host "Installing dependencies..." -ForegroundColor Cyan
        $pipResult = & $venvPython -m pip install -r $requirements 2>&1
        if ($pipResult) {
            $pipResult | ForEach-Object { Write-Host $_ }
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to install dependencies."
        }
        New-Item -ItemType File -Path $stamp -Force | Out-Null
    }

    return ,$venvPython
}

$python = Ensure-Venv

$args = @("agent.py", "--transport", $Transport, "--baud", $Baud, "--interval", $Interval, "--gpu-index", $GpuIndex)

if ($Transport -in @("serial", "auto")) {
    if (-not $Port) {
        $detected = @(Get-Esp32ComPorts)
        $Port = Select-ComPort -Candidates $detected
    }
    $args += @("--port", $Port)
    Write-Host "Using serial port: $Port" -ForegroundColor Cyan
}

if ($Transport -in @("wifi", "auto")) {
    $envFile = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
    if (-not (Test-Path $envFile)) {
        Write-Host "Warning: .env not found. Copy .env.example to .env and set WiFi credentials." -ForegroundColor Yellow
    }
    if ($WifiHost) {
        $args += @("--wifi-host", $WifiHost)
    }
    if ($WifiPort -gt 0) {
        $args += @("--wifi-port", $WifiPort)
    }
    Write-Host "Transport: $Transport (mDNS discovery)" -ForegroundColor Cyan
}

Write-Host "Starting PC agent (Ctrl+C to stop)..." -ForegroundColor Cyan
& $python @args
exit $LASTEXITCODE
