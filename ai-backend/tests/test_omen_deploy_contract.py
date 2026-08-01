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
