# ESP32 PC Monitor Display

Turn a [Waveshare ESP32-S3-Touch-LCD-3.49](https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-3.49) into a compact PC stats display showing GPU usage, temperature, VRAM, CPU, RAM, and system volume.

The board has a narrow **172×640** IPS panel — ideal for a vertical dashboard beside your monitor.

## Architecture

```text
┌─────────────┐  USB serial or WiFi   ┌──────────────────┐
│  Windows PC │ ────── (JSON) ──────► │  ESP32-S3 board  │
│  pc-agent   │                       │  LVGL dashboard  │
└─────────────┘                       └──────────────────┘
```

**PC agent** (`pc-agent/`) reads system metrics and sends one JSON line per second over **USB serial** or **WiFi TCP**.

**Firmware** (`firmware/`) renders the metrics with LVGL on the built-in display.

### JSON protocol

Each line is a JSON object terminated by `\n`:

```json
{"gpu":45,"gpu_temp":62,"gpu_mem":78,"cpu":23,"ram":56,"vol":67,"muted":false}
```

| Field | Description |
|-------|-------------|
| `gpu` | GPU utilization (0–100) |
| `gpu_temp` | GPU temperature (°C) |
| `gpu_mem` | VRAM usage (0–100) |
| `cpu` | CPU usage (0–100) |
| `ram` | RAM usage (0–100) |
| `vol` | Master volume (0–100) |
| `muted` | `true` if muted |

## Prerequisites

### Hardware
- Waveshare ESP32-S3-Touch-LCD-3.49
- USB-C cable (data-capable)

### Software
- [PlatformIO](https://platformio.org/) (`pip install platformio`)
- Python 3.10+

This project uses the [pioarduino](https://github.com/pioarduino/platform-espressif32) platform fork because Waveshare's drivers require **Arduino-ESP32 3.x** (ESP-IDF 5.x APIs).

## Quick start

### 0. WiFi setup (optional)

Copy the example env file and add your network credentials:

```powershell
copy .env.example .env
```

Edit `.env`:

```env
WIFI_SSID=YourWiFiName
WIFI_PASSWORD=YourWiFiPassword
DEVICE_HOSTNAME=esp32-pc-monitor
STATS_PORT=5000
```

`.env` is gitignored. Firmware reads it at build time; the PC agent reads it at runtime for mDNS discovery.

After flashing with WiFi configured, the display joins your network and advertises itself as `<DEVICE_HOSTNAME>.local` on port `STATS_PORT`.

### 1. Flash the firmware

```powershell
cd firmware
pio run -t upload
pio device monitor
```

If upload fails, hold **BOOT**, tap **RESET**, release **BOOT**, then retry upload.

Set the serial port explicitly if needed:

```powershell
pio run -t upload --upload-port COM5
pio device monitor --port COM5
```

### 2. Run the PC agent

**USB serial** (default):

```powershell
cd pc-agent
.\run.ps1
```

**WiFi** (discovers the display via mDNS):

```powershell
cd pc-agent
.\run.ps1 -Transport wifi
```

**Auto** (try WiFi first, fall back to USB):

```powershell
.\run.ps1 -Transport auto
```

Manual usage:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python agent.py --list-ports
python agent.py --port COM5
python agent.py --transport wifi
python agent.py --transport auto
```

GPU stats require an **NVIDIA** GPU and the `pynvml` package. Volume control uses **Windows** audio APIs via `pycaw`. CPU and RAM work on any platform.

## Project layout

```text
ESP32 Display/
├── firmware/           PlatformIO project (ESP32 + LVGL UI)
│   ├── platformio.ini
│   └── src/
│       ├── main.cpp    Serial JSON parser
│       ├── stats_ui.c  Dashboard widgets
│       └── board/      Waveshare display drivers (from vendor demo)
├── pc-agent/           Python metrics sender
│   ├── agent.py
│   └── requirements.txt
└── vendor/waveshare/   Official Waveshare board repo (cloned)
```

Board support files are copied from Waveshare's `10_LVGL_V9_Test` Arduino example. See [waveshareteam/ESP32-S3-Touch-LCD-3.49](https://github.com/waveshareteam/ESP32-S3-Touch-LCD-3.49).

## Next steps

- **Touch controls** — use the capacitive panel to mute/unmute or switch pages
- **Custom themes** — tweak `stats_ui.c` colors and layout for your desk setup
- **More metrics** — network throughput, disk usage, per-core CPU, fan speeds

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Blank display after flash | Confirm USB power; check serial monitor for boot logs |
| `Waiting for PC...` stuck | Run `agent.py` on the correct COM port at 115200 baud, or use `--transport wifi` |
| WiFi connect failed | Check `.env` credentials; re-flash firmware after editing `.env` |
| Agent can't find display on WiFi | PC and ESP32 must be on the same network; verify mDNS (`esp32-pc-monitor.local`) |
| GPU always 0 | Install NVIDIA drivers; verify `pynvml` import works |
| Volume always 0 | Run agent on Windows; install `pycaw` and `comtypes` |
| Upload timeout | Use boot-mode sequence above; try a lower `upload_speed` in `platformio.ini` |
| Build errors about `i2c_master.h` | Ensure `platformio.ini` uses the pioarduino platform URL |
