# Build and flash firmware to the Waveshare ESP32-S3 board.
# Auto-detects the COM port (Espressif USB VID 303A).

param(
    [string]$Port,
    [switch]$Monitor,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Get-Esp32ComPorts {
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

function Select-ComPort {
    param([System.Collections.IEnumerable]$Candidates)

    if ($Candidates.Count -eq 0) {
        Write-Host ""
        Write-Host "No ESP32 COM port found." -ForegroundColor Red
        Write-Host "  - Plug in the board via USB"
        Write-Host "  - Close the PC agent / serial monitor (they lock the port)"
        Write-Host "  - Run: pio device list"
        exit 1
    }

    if ($Candidates.Count -eq 1) {
        return $Candidates[0].Port
    }

    Write-Host "Multiple ESP32 ports found:" -ForegroundColor Yellow
    for ($i = 0; $i -lt $Candidates.Count; $i++) {
        $item = $Candidates[$i]
        Write-Host ("  [{0}] {1} - {2}" -f ($i + 1), $item.Port, $item.Details)
    }

    $choice = Read-Host "Select port number"
    $index = [int]$choice - 1
    if ($index -lt 0 -or $index -ge $Candidates.Count) {
        Write-Error "Invalid selection."
    }
    return $Candidates[$index].Port
}

if (-not $Port) {
    $detected = @(Get-Esp32ComPorts)
    $Port = Select-ComPort -Candidates $detected
}

Write-Host "Using port: $Port" -ForegroundColor Cyan

if (-not $SkipBuild) {
    Write-Host "Building firmware..." -ForegroundColor Cyan
    pio run
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Uploading to $Port..." -ForegroundColor Cyan
pio run -t upload --upload-port $Port
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Upload failed. Try boot mode:" -ForegroundColor Yellow
    Write-Host "  1. Hold BOOT"
    Write-Host "  2. Press RESET"
    Write-Host "  3. Release RESET, then BOOT"
    Write-Host "  4. Run: .\flash.ps1 -Port $Port"
    exit $LASTEXITCODE
}

Write-Host "Flash complete." -ForegroundColor Green

if ($Monitor) {
    Write-Host "Opening serial monitor on $Port (Ctrl+C to exit)..." -ForegroundColor Cyan
    pio device monitor --port $Port
}
