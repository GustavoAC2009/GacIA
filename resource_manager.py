"""Gerenciamento local e conservador de recursos de GPU.

Não coleta nem transmite telemetria. Quando disponível, consulta o nvidia-smi
local em uma thread própria; as decisões de tarefas opcionais usam um snapshot
cacheado e não são executadas no caminho de streaming do Ollama.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from functools import wraps
from typing import Callable

LOGGER = logging.getLogger("GacIA.Resources")

@dataclass(frozen=True)
class GPUStatus:
    name: str
    temperature_c: int | None
    utilization_percent: int | None
    memory_total_mb: int | None
    memory_used_mb: int | None
    memory_free_mb: int | None
    captured_at: float
    fan_percent: int | None = None
    power_draw_w: float | None = None
    power_limit_w: float | None = None
    max_temperature_c: int | None = None
    max_operating_temp_c: int | None = None
    slowdown_temp_c: int | None = None

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.captured_at)


_lock = threading.RLock()
GPU_TASK_LOCK = threading.RLock()
_cached_status: GPUStatus | None = None
_cache_ttl = 8.0


def serialize_gpu_task(func=None, *, wait_if_hot: bool = True):
    """Serializa tarefas de GPU e, por padrão, espera a placa esfriar.

    Tarefas com fallback seguro para CPU podem desativar a espera e decidir o
    backend por conta própria. Isso evita bloquear a interface/instalação por
    até 15 minutos quando, por exemplo, o Whisper pode simplesmente usar CPU.
    """
    def decorate(task):
        @wraps(task)
        def wrapper(*args, **kwargs):
            with GPU_TASK_LOCK:
                if wait_if_hot:
                    status = get_gpu_status(refresh=True)
                    if status is not None:
                        temperatures = [value for value in (status.temperature_c, status.max_temperature_c) if value is not None]
                        temperature = max(temperatures) if temperatures else None
                        safe_limit = min(75, status.max_operating_temp_c - 15) if status.max_operating_temp_c else 75
                        if temperature is not None and temperature >= safe_limit:
                            status_callback = kwargs.get("status_callback")
                            owner = args[0] if args else None
                            if not callable(status_callback) and callable(getattr(owner, "_emit_status", None)):
                                status_callback = lambda message: owner._emit_status("warning", message)
                            cancel_callback = kwargs.get("cancel_callback")
                            if not callable(cancel_callback) and getattr(owner, "cancel_event", None) is not None:
                                cancel_callback = owner.cancel_event.is_set
                            ready, reason = wait_for_gpu_resources(
                                purpose=task.__name__, min_free_mb=0, max_wait_seconds=900,
                                poll_seconds=10, status_callback=status_callback,
                                cancel_callback=cancel_callback,
                            )
                            if not ready:
                                raise RuntimeError(reason)
                return task(*args, **kwargs)
        return wrapper
    return decorate(func) if func is not None else decorate


def _query_nvidia_smi(timeout: float = 1.5) -> GPUStatus | None:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    command = [
        executable,
        "--query-gpu=name,temperature.gpu,utilization.gpu,memory.total,memory.used,memory.free,fan.speed,power.draw,power.limit",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        # A Gac.IA target commonly has one discrete NVIDIA GPU. Select the
        # first usable adapter; multi-GPU selection can be added explicitly later.
        line = next((item.strip() for item in result.stdout.splitlines() if item.strip()), "")
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 6:
            return None
        def number(value: str) -> int | None:
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None
        def decimal(value: str) -> float | None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        thermal = subprocess.run(
            [executable, "-q", "-d", "TEMPERATURE"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        def thermal_value(label: str) -> int | None:
            match = re.search(rf"^\s*{re.escape(label)}\s*:\s*(\d+)\s*C\s*$", thermal.stdout or "", re.M)
            return int(match.group(1)) if match else None
        return GPUStatus(
            name=parts[0] or "NVIDIA GPU",
            temperature_c=number(parts[1]),
            utilization_percent=number(parts[2]),
            memory_total_mb=number(parts[3]),
            memory_used_mb=number(parts[4]),
            memory_free_mb=number(parts[5]),
            captured_at=time.monotonic(),
            fan_percent=number(parts[6]) if len(parts) > 6 else None,
            power_draw_w=decimal(parts[7]) if len(parts) > 7 else None,
            power_limit_w=decimal(parts[8]) if len(parts) > 8 else None,
            max_temperature_c=thermal_value("GPU Current Max Temp"),
            max_operating_temp_c=thermal_value("GPU Max Operating Temp"),
            slowdown_temp_c=thermal_value("GPU Slowdown Temp"),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        LOGGER.debug("Leitura local do nvidia-smi indisponível: %s", exc)
        return None


def get_gpu_status(*, refresh: bool = False, max_age: float | None = None) -> GPUStatus | None:
    """Retorna snapshot local cacheado; refresh é usado apenas por workers."""
    global _cached_status
    ttl = _cache_ttl if max_age is None else max(0.0, float(max_age))
    with _lock:
        cached = _cached_status
        if not refresh and cached is not None and cached.age_seconds <= ttl:
            return cached
    status = _query_nvidia_smi()
    if status is not None:
        with _lock:
            _cached_status = status
    return status


def set_cached_gpu_status_for_tests(status: GPUStatus | None) -> None:
    global _cached_status
    with _lock:
        _cached_status = status


def whisper_backend_decision(status: GPUStatus | None) -> tuple[str, str]:
    """Decide CUDA vs CPU para Whisper; nunca concorre deliberadamente com GPU quente."""
    if status is None:
        return "cpu", "sensor NVIDIA indisponível; usando CPU para não assumir risco térmico"
    temperatures = [value for value in (status.temperature_c, status.max_temperature_c) if value is not None]
    temperature = max(temperatures) if temperatures else None
    safe_limit = min(75, status.max_operating_temp_c - 15) if status.max_operating_temp_c else 75
    if temperature is not None and temperature >= safe_limit:
        return "cpu", f"GPU a {temperature} °C; Whisper ficará na CPU até a placa esfriar"
    if status.utilization_percent is not None and status.utilization_percent >= 45:
        return "cpu", f"GPU ocupada ({status.utilization_percent}%); Whisper ficará na CPU"
    if status.memory_free_mb is not None and status.memory_free_mb < 2500:
        return "cpu", f"VRAM livre insuficiente ({status.memory_free_mb} MB); Whisper ficará na CPU"
    return "cuda", "temperatura, utilização e VRAM permitem Whisper em CUDA"


def image_gpu_decision(status: GPUStatus | None, *, reuse_loaded_model: bool = False) -> tuple[bool, str]:
    """Bloqueia cargas pesadas; permite menor folga ao reutilizar o mesmo modelo já carregado."""
    if status is None:
        # Sem telemetria local não se presume que uma placa esteja saudável;
        # porém também não se bloqueiam GPUs AMD/Intel/CPU por falta de nvidia-smi.
        return True, "sensor NVIDIA indisponível; prosseguindo sem proteção térmica NVIDIA"
    temperatures = [value for value in (status.temperature_c, status.max_temperature_c) if value is not None]
    temperature = max(temperatures) if temperatures else None
    safe_limit = min(75, status.max_operating_temp_c - 15) if status.max_operating_temp_c else 75
    if temperature is not None and temperature >= safe_limit:
        return False, f"GPU a {temperature} °C; nova geração de imagem aguarda até a temperatura cair abaixo de {safe_limit} °C."
    if status.utilization_percent is not None and status.utilization_percent >= 80:
        return False, f"Geração de imagem pausada: GPU já está ocupada ({status.utilization_percent}%). Isso evita competir com a resposta do modelo."
    if status.memory_free_mb is not None:
        minimo = 2000 if reuse_loaded_model else 3500
        if status.memory_free_mb < minimo:
            if reuse_loaded_model:
                motivo = "VRAM livre insuficiente para continuar com segurança"
            else:
                motivo = "VRAM livre insuficiente para carregar o modelo de imagem"
            return False, f"Geração de imagem pausada: {motivo} ({status.memory_free_mb} MB livres; mínimo {minimo} MB)."
    return True, "GPU disponível para uma tarefa de imagem"


def wait_for_gpu_resources(
    *, purpose: str = "tarefa de GPU", min_free_mb: int = 3500,
    max_wait_seconds: float = 900, poll_seconds: float = 10,
    status_callback: Callable[[str], None] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> tuple[bool, str]:
    """Espera a GPU esfriar e liberar VRAM antes de uma carga local pesada."""
    started = time.monotonic()
    while True:
        if cancel_callback and cancel_callback():
            return False, f"Espera por recursos para {purpose} cancelada."
        status = get_gpu_status(refresh=True)
        if status is None:
            return True, "Sensor NVIDIA indisponível; prosseguindo sem telemetria térmica."
        temperatures = [value for value in (status.temperature_c, status.max_temperature_c) if value is not None]
        temperature = max(temperatures) if temperatures else None
        cool_limit = min(70, status.max_operating_temp_c - 20) if status.max_operating_temp_c else 70
        utilization_ok = status.utilization_percent is None or status.utilization_percent < 80
        memory_ok = status.memory_free_mb is None or status.memory_free_mb >= min_free_mb
        temperature_ok = temperature is None or temperature < cool_limit
        if utilization_ok and memory_ok and temperature_ok:
            return True, f"GPU liberada para {purpose}: {temperature if temperature is not None else 'temperatura indisponível'} °C, {status.memory_free_mb if status.memory_free_mb is not None else 'VRAM indisponível'} MB livres."
        elapsed = time.monotonic() - started
        if elapsed >= max(0, float(max_wait_seconds)):
            return False, f"Tempo de espera por recursos para {purpose} excedido após {int(elapsed)} s (temperatura {temperature if temperature is not None else 'indisponível'} °C, VRAM livre {status.memory_free_mb if status.memory_free_mb is not None else 'indisponível'} MB)."
        if status_callback:
            status_callback(
                f"GPU aguardando para {purpose} · {temperature if temperature is not None else '?'} °C · "
                f"{status.memory_free_mb if status.memory_free_mb is not None else '?'} MB livres · "
                f"{int(elapsed)} s"
            )
        time.sleep(max(1.0, min(float(poll_seconds), float(max_wait_seconds) - elapsed)))


class GPUStatusMonitor:
    """Monitor passivo local, sem chamadas de rede nem bloqueio da UI."""
    def __init__(self, callback: Callable[[GPUStatus | None], None] | None = None, interval: float = 20.0):
        self.callback = callback
        self.interval = max(10.0, float(interval))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="GacIA-GPU-Monitor", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        # primeira leitura imediata ocorre fora da thread da interface
        while not self._stop.is_set():
            status = get_gpu_status(refresh=True)
            if self.callback:
                try:
                    self.callback(status)
                except Exception:
                    LOGGER.debug("Callback do monitor GPU falhou.", exc_info=True)
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()

