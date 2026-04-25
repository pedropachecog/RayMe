# STT GPU Runtime

RayMe STT uses `faster-whisper` through CTranslate2 and is expected to run on
the OMEN RTX 3060 GPU for call-latency work. CPU fallback is not an acceptable
production path for the phone-call simulator.

## OMEN Baseline

- SSH target: `ssh rayme-pmpg`
- Runtime checkout: `C:\Users\pmpg\rayme\RayMe`
- AI venv: `C:\Users\pmpg\rayme\RayMe\ai-backend\.venv`
- Driver observed on 2026-04-25: NVIDIA 560.94, CUDA driver support 12.6
- Required CTranslate2 GPU libraries: CUDA cuBLAS and cuDNN on the process
  `PATH`
- CUDA runtime directory:
  `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin`

## Failure Signature

If STT fails with:

```text
RuntimeError: Library cublas64_12.dll is not found or cannot be loaded
```

then CTranslate2 is trying to run on CUDA, but the Windows runtime cannot find
CUDA 12 cuBLAS. Installing or exposing `cublas64_12.dll` is the fix; switching
to CPU is not.

## Required Fix

Install NVIDIA CUDA Toolkit 12.6 on OMEN or otherwise provide a durable CUDA 12
runtime directory containing `cublas64_12.dll`, `cublasLt64_12.dll`,
`cudart64_12.dll`, and the required cuDNN 9 DLLs. The scheduled AI backend
startup must prepend that CUDA `bin` directory to `PATH` before launching
Python.

If the full CUDA Toolkit installer cannot complete without elevation, extract
the runtime DLLs from the verified NVIDIA CUDA 12.6 installer with 7-Zip into a
durable RayMe-owned runtime directory, then update `scripts/deploy-omen.sh` to
prepend that directory. The installed OMEN runtime layout is:

```text
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin\cublas64_12.dll
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin\cublasLt64_12.dll
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin\cudart64_12.dll
```

Do not install CUDA 13.x for this runtime unless CTranslate2 and the NVIDIA
driver baseline are intentionally updated and revalidated. OMEN currently has
driver support for CUDA 12.6.

## Verification

Run against a real saved voice sample:

```powershell
cd C:\Users\pmpg\rayme\RayMe\ai-backend
set PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin;%PATH%
.\.venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; m=WhisperModel('distil-large-v3', device='cuda', compute_type='int8_float16'); print('cuda-ready')"
```

Then verify the live API:

```bash
curl -k -sS -X POST \
  -F 'file=@/tmp/rayme-libb-sample.wav;type=audio/wav;filename=Stamets-Sample-Short.wav' \
  https://192.168.1.199:9443/stt/transcribe
```

The response must be HTTP 200 and must report `"compute_type":"int8_float16"`,
not CPU `int8`.
