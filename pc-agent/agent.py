"""Collect PC metrics and send them to the ESP32 display over USB serial or WiFi."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)

import psutil
import serial
import serial.tools.list_ports
from dotenv import load_dotenv

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        import pynvml

    HAS_NVML = True
except ImportError:
    HAS_NVML = False

try:
    from pycaw.pycaw import AudioUtilities

    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False

try:
    from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False


ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"
DEFAULT_HOSTNAME = "esp32-pc-monitor"
DEFAULT_PORT = 5000
MDNS_SERVICE = "_pcmonitor._tcp.local."
DISCOVERY_TIMEOUT = 5.0


@dataclass
class AgentConfig:
    transport: str = "serial"
    port: str | None = None
    baud: int = 115200
    interval: float = 1.0
    gpu_index: int = 0
    wifi_host: str | None = None
    wifi_port: int = DEFAULT_PORT
    discover_timeout: float = DISCOVERY_TIMEOUT


@dataclass
class EnvSettings:
    wifi_ssid: str = ""
    wifi_password: str = ""
    device_hostname: str = DEFAULT_HOSTNAME
    stats_port: int = DEFAULT_PORT


def load_settings() -> EnvSettings:
    load_dotenv(ENV_FILE)
    import os

    hostname = os.getenv("DEVICE_HOSTNAME", DEFAULT_HOSTNAME).strip().lower() or DEFAULT_HOSTNAME
    port_raw = os.getenv("STATS_PORT", str(DEFAULT_PORT)).strip()
    return EnvSettings(
        wifi_ssid=os.getenv("WIFI_SSID", "").strip(),
        wifi_password=os.getenv("WIFI_PASSWORD", "").strip(),
        device_hostname=hostname,
        stats_port=int(port_raw) if port_raw.isdigit() else DEFAULT_PORT,
    )


def list_serial_ports() -> list[str]:
    return [port.device for port in serial.tools.list_ports.comports()]


def pick_port(explicit_port: str | None) -> str:
    if explicit_port:
        return explicit_port

    ports = list_serial_ports()
    preferred = [p for p in ports if "USB" in p.upper() or "COM" in p.upper()]
    candidates = preferred or ports
    if not candidates:
        raise RuntimeError("No serial ports found. Connect the ESP32 over USB and try again.")
    if len(candidates) == 1:
        return candidates[0]

    print("Multiple serial ports found:")
    for index, port in enumerate(candidates, start=1):
        print(f"  {index}. {port}")
    choice = input("Select port number: ").strip()
    return candidates[int(choice) - 1]


class GpuMonitor:
    def __init__(self, gpu_index: int) -> None:
        self.available = False
        self.gpu_index = gpu_index
        if not HAS_NVML:
            return
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                pynvml.nvmlInit()
            self.handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
            self.available = True
        except Exception as exc:  # noqa: BLE001 - optional hardware path
            print(f"GPU monitoring unavailable: {exc}", file=sys.stderr)

    def read(self) -> tuple[int, int, int]:
        if not self.available:
            return 0, 0, 0

        util = pynvml.nvmlDeviceGetUtilizationRates(self.handle)
        temp = pynvml.nvmlDeviceGetTemperature(self.handle, pynvml.NVML_TEMPERATURE_GPU)
        mem = pynvml.nvmlDeviceGetMemoryInfo(self.handle)
        mem_percent = int((mem.used / mem.total) * 100) if mem.total else 0
        return int(util.gpu), int(temp), mem_percent


class VolumeMonitor:
    def __init__(self) -> None:
        self.available = False
        self.volume = None
        if not HAS_PYCAW:
            return
        try:
            device = AudioUtilities.GetSpeakers()
            self.volume = device.EndpointVolume
            self.available = True
        except Exception as exc:  # noqa: BLE001 - optional Windows audio path
            print(f"Volume monitoring unavailable: {exc}", file=sys.stderr)

    def read(self) -> tuple[int, bool]:
        if not self.available or self.volume is None:
            return 0, False

        muted = bool(self.volume.GetMute())
        level = self.volume.GetMasterVolumeLevelScalar()
        return int(max(0.0, min(1.0, level)) * 100), muted


def collect_metrics(gpu: GpuMonitor, volume: VolumeMonitor) -> dict[str, int | bool]:
    gpu_usage, gpu_temp, gpu_mem = gpu.read()
    vol, muted = volume.read()
    return {
        "gpu": gpu_usage,
        "gpu_temp": gpu_temp,
        "gpu_mem": gpu_mem,
        "cpu": int(psutil.cpu_percent(interval=None)),
        "ram": int(psutil.virtual_memory().percent),
        "vol": vol,
        "muted": muted,
    }


def open_serial(port: str, baud: int) -> serial.Serial:
    try:
        return serial.Serial(port, baud, timeout=1, write_timeout=1)
    except serial.SerialException as exc:
        message = str(exc).lower()
        if "access is denied" in message or "permission" in message:
            raise RuntimeError(
                f"Could not open {port}: port is in use.\n"
                "Close pio device monitor, any other agent instance, or Arduino Serial Monitor, then retry."
            ) from exc
        if "could not open port" in message and "filenotfound" in message.replace(" ", ""):
            raise RuntimeError(
                f"Could not open {port}: port not found.\n"
                "Plug in the ESP32 and run: python agent.py --list-ports"
            ) from exc
        raise


def discover_wifi_target(hostname: str, port: int, timeout: float) -> tuple[str, int]:
    if not HAS_ZEROCONF:
        raise RuntimeError("WiFi discovery requires the 'zeroconf' package. Run: pip install -r requirements.txt")

    found: dict[str, tuple[str, int]] = {}
    service_name = f"{hostname}.{MDNS_SERVICE}"

    class Browser:
        def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            pass

        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name, timeout=1000)
            if not info or not info.addresses:
                return
            address = socket.inet_ntoa(info.addresses[0])
            service_port = info.port or port
            found[name] = (address, service_port)

        def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            self.add_service(zc, type_, name)

    zeroconf = Zeroconf()
    try:
        print(f"Discovering {MDNS_SERVICE} (timeout {timeout:.0f}s)...", flush=True)
        browser = ServiceBrowser(zeroconf, MDNS_SERVICE, Browser())
        deadline = time.time() + timeout
        while time.time() < deadline and not found:
            time.sleep(0.1)

        if service_name in found:
            return found[service_name]

        if found:
            name, endpoint = next(iter(found.items()))
            print(f"Using discovered service {name}", flush=True)
            return endpoint

        # Fallback: resolve <hostname>.local directly.
        try:
            addrinfo = socket.getaddrinfo(f"{hostname}.local", port, type=socket.SOCK_STREAM)
            address = addrinfo[0][4][0]
            print(f"Resolved {hostname}.local -> {address}", flush=True)
            return address, port
        except socket.gaierror as exc:
            raise RuntimeError(
                f"Could not find ESP32 on the network.\n"
                f"  - Ensure the display is powered and connected to WiFi\n"
                f"  - Check .env DEVICE_HOSTNAME matches the firmware ({hostname})\n"
                f"  - Try USB serial instead: python agent.py --transport serial"
            ) from exc
    finally:
        zeroconf.close()


def open_wifi(host: str | None, port: int, settings: EnvSettings, timeout: float) -> socket.socket:
    hostname = (host or settings.device_hostname).strip().lower()
    if host and host.replace(".", "").isdigit():
        address = host
        target_port = port
    else:
        address, target_port = discover_wifi_target(hostname, port, timeout)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((address, target_port))
    except OSError as exc:
        raise RuntimeError(
            f"Could not connect to {address}:{target_port}.\n"
            "Ensure the ESP32 is on the same network and WiFi is enabled in firmware."
        ) from exc

    sock.settimeout(None)
    print(f"Connected over WiFi to {address}:{target_port}", flush=True)
    return sock


def run_serial_loop(config: AgentConfig, gpu: GpuMonitor, volume: VolumeMonitor) -> None:
    port = pick_port(config.port)
    print(f"Opening {port} at {config.baud} baud", flush=True)
    print("Press Ctrl+C to stop", flush=True)

    with open_serial(port, config.baud) as ser:
        time.sleep(3)
        psutil.cpu_percent(interval=None)

        while True:
            payload = collect_metrics(gpu, volume)
            line = json.dumps(payload, separators=(",", ":")) + "\n"
            print(line.strip(), flush=True)
            try:
                ser.write(line.encode("utf-8"))
            except serial.SerialTimeoutException:
                print("Warning: serial write timed out (display may still be booting)", file=sys.stderr, flush=True)
            time.sleep(config.interval)


def run_wifi_loop(config: AgentConfig, settings: EnvSettings, gpu: GpuMonitor, volume: VolumeMonitor) -> None:
    print("Press Ctrl+C to stop", flush=True)
    sock = open_wifi(config.wifi_host, config.wifi_port, settings, config.discover_timeout)
    psutil.cpu_percent(interval=None)

    try:
        while True:
            payload = collect_metrics(gpu, volume)
            line = json.dumps(payload, separators=(",", ":")) + "\n"
            print(line.strip(), flush=True)
            try:
                sock.sendall(line.encode("utf-8"))
            except OSError as exc:
                raise RuntimeError("WiFi connection lost. Restart the agent to reconnect.") from exc
            time.sleep(config.interval)
    finally:
        sock.close()


def run(config: AgentConfig) -> None:
    settings = load_settings()
    gpu = GpuMonitor(config.gpu_index)
    volume = VolumeMonitor()

    if config.transport == "wifi":
        run_wifi_loop(config, settings, gpu, volume)
        return

    if config.transport == "auto":
        try:
            run_wifi_loop(config, settings, gpu, volume)
            return
        except RuntimeError as exc:
            print(f"WiFi unavailable ({exc}); falling back to USB serial.", file=sys.stderr, flush=True)

    run_serial_loop(config, gpu, volume)


def parse_args() -> AgentConfig:
    parser = argparse.ArgumentParser(description="Send PC stats to the ESP32 display")
    parser.add_argument(
        "--transport",
        choices=["serial", "wifi", "auto"],
        default="serial",
        help="serial=USB, wifi=network only, auto=try WiFi then USB",
    )
    parser.add_argument("--port", help="Serial port, e.g. COM5")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--wifi-host", help="ESP32 IP or mDNS hostname (default: DEVICE_HOSTNAME from .env)")
    parser.add_argument("--wifi-port", type=int, help="TCP port (default: STATS_PORT from .env)")
    parser.add_argument("--discover-timeout", type=float, default=DISCOVERY_TIMEOUT, help="mDNS discovery seconds")
    parser.add_argument("--interval", type=float, default=1.0, help="Update interval in seconds")
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--list-ports", action="store_true", help="List serial ports and exit")
    args = parser.parse_args()

    if args.list_ports:
        for port in list_serial_ports():
            print(port)
        raise SystemExit(0)

    settings = load_settings()
    return AgentConfig(
        transport=args.transport,
        port=args.port,
        baud=args.baud,
        interval=args.interval,
        gpu_index=args.gpu_index,
        wifi_host=args.wifi_host,
        wifi_port=args.wifi_port or settings.stats_port,
        discover_timeout=args.discover_timeout,
    )


if __name__ == "__main__":
    try:
        run(parse_args())
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
