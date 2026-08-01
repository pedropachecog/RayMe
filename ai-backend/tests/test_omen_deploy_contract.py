from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy-omen.sh"


def test_omen_deploy_allows_aiortc_udp_only_for_rayme_runtime_and_lan() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert '$aiPythonw = Join-Path $repo "ai-backend\\.venv\\Scripts\\pythonw.exe"' in source
    assert 'Name = "RayMeAIWebRTCMediaUDP"' in source
    assert "-Program $aiProcessImage" in source
    assert "-Protocol UDP" in source
    assert "-RemoteAddress LocalSubnet" in source
    assert "-Profile Any" in source
    assert "Get-NetFirewallApplicationFilter -AssociatedNetFirewallRule" in source
    assert "Get-NetFirewallAddressFilter -AssociatedNetFirewallRule" in source


def test_omen_deploy_targets_live_windows_python_image_for_aiortc_udp() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "sys._base_executable" in source
    assert '$aiProcessImage = [string]$aiProcessIdentity.base_pythonw' in source
    assert "-Program $aiProcessImage" in source
    assert "$liveAiProcess.ExecutablePath" in source
    assert "$applicationFilter.Program" in source
    assert "RayMe AI process image does not match the WebRTC firewall rule" in source


def test_default_omen_deploy_provisions_and_attests_qwen_before_launch() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    unconditional_provision = "Stop-RayMePortOwners\nInvoke-RayMeQwen3Provisioning"
    launcher_write = 'Write-Host "== Writing scheduled task launchers"'
    assert unconditional_provision in source
    assert source.index(unconditional_provision) < source.index(launcher_write)
    assert "if ($verifyQwen3Tracer -or $verifyQwen3 -or $qwenFidelitySweep)" not in source

    health_gate = source[source.index('Write-Host "== Verifying health"') :]
    assert 'Join-Path $qwenModelDir "rayme-model-revision.json"' in health_gate
    assert "$script:QwenRuntimeIdentity.runtime_source_commit" in health_gate
    assert "$script:QwenRuntimeIdentity.model_revision" in health_gate
    assert "$qwenManifest.model_id" in health_gate
    assert "$qwenManifest.model_revision" in health_gate
    assert '$_.id -eq "qwen3_1_7b"' in health_gate
    assert "$qwenEngineStatus.available -eq $false" in health_gate
    assert 'https://192.168.1.199:9443/webrtc/status' in health_gate
    assert "$webrtcStatus.live_call_ready" in health_gate
    assert "$webrtcStatus.deployed_commit -ne $actualHead" in health_gate
