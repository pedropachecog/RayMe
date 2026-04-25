from __future__ import annotations

from dataclasses import dataclass


class GpuRuntimeError(RuntimeError):
    """Raised when a production AI model would run without CUDA acceleration."""


@dataclass(frozen=True)
class GpuRuntimeInfo:
    component: str
    torch_version: str
    torch_cuda_version: str
    device_name: str


def require_cuda_device_config(
    *,
    component: str,
    device: str,
    compute_type: str | None = None,
) -> None:
    normalized_device = (device or "").strip().lower()
    if normalized_device != "cuda":
        raise GpuRuntimeError(
            f"{component} requires CUDA device execution; configured device={device!r}."
        )

    normalized_compute = (compute_type or "").strip().lower()
    if normalized_compute and "float16" not in normalized_compute:
        raise GpuRuntimeError(
            f"{component} requires a CUDA float16-capable compute type; "
            f"configured compute_type={compute_type!r}."
        )


def require_torch_cuda_runtime(component: str) -> GpuRuntimeInfo:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - depends on deployment image
        raise GpuRuntimeError(f"{component} requires PyTorch with CUDA support.") from exc

    version = str(getattr(torch, "__version__", "unknown"))
    torch_version = getattr(torch, "version", None)
    cuda_version = str(getattr(torch_version, "cuda", "") or "")
    cuda_api = getattr(torch, "cuda", None)
    cuda_available = bool(cuda_api and cuda_api.is_available())

    if "+cpu" in version.lower() or not cuda_version or not cuda_available:
        raise GpuRuntimeError(
            f"{component} requires a CUDA-enabled PyTorch runtime; "
            f"torch={version}, torch_cuda={cuda_version or 'none'}, "
            f"cuda_available={cuda_available}."
        )

    try:
        device_name = str(cuda_api.get_device_name(0))
    except Exception:  # pragma: no cover - informational only
        device_name = "cuda:0"

    return GpuRuntimeInfo(
        component=component,
        torch_version=version,
        torch_cuda_version=cuda_version,
        device_name=device_name,
    )

