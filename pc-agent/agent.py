"""Collect PC metrics and send them to the ESP32 display over USB serial."""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from dataclasses import dataclass

warnings.filterwarnings("ignore", category=FutureWarning)

import psutil
import serial
import serial.tools.list_ports

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


@dataclass
class AgentConfig:
    port: str | None = None
    baud: int = 115200
    interval: float = 1.0
    gpu_index: int = 0


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


def run(config: AgentConfig) -> None:
    port = pick_port(config.port)
    gpu = GpuMonitor(config.gpu_index)
    volume = VolumeMonitor()

    print(f"Opening {port} at {config.baud} baud", flush=True)
    print("Press Ctrl+C to stop", flush=True)

    with open_serial(port, config.baud) as ser:
        # Opening the port resets the ESP32; give firmware time to boot.
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


def parse_args() -> AgentConfig:
    parser = argparse.ArgumentParser(description="Send PC stats to the ESP32 display")
    parser.add_argument("--port", help="Serial port, e.g. COM5")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--interval", type=float, default=1.0, help="Update interval in seconds")
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--list-ports", action="store_true", help="List serial ports and exit")
    args = parser.parse_args()

    if args.list_ports:
        for port in list_serial_ports():
            print(port)
        raise SystemExit(0)

    return AgentConfig(
        port=args.port,
        baud=args.baud,
        interval=args.interval,
        gpu_index=args.gpu_index,
    )


if __name__ == "__main__":
    try:
        run(parse_args())
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
