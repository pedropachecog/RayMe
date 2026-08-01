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
    assert "$script:QwenRuntimeIdentity.runtime_source_repository" in health_gate
    assert "$script:QwenRuntimeIdentity.runtime_source_vcs" in health_gate
    assert "$script:QwenRuntimeIdentity.model_revision" in health_gate
    assert "$qwenManifest.model_id" in health_gate
    assert "$qwenManifest.model_revision" in health_gate
    assert '$_.id -eq "qwen3_1_7b"' in health_gate
    assert "$qwenEngineStatus.available -eq $false" in health_gate
    assert 'https://192.168.1.199:9443/webrtc/status' in health_gate
    assert "$webrtcStatus.live_call_ready" in health_gate
    assert "$webrtcStatus.deployed_commit -ne $actualHead" in health_gate


def test_omen_deploy_upgrades_persistent_web_schema_before_launch() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    services_stopped = "Stop-RayMePortOwners\nInvoke-RayMeQwen3Provisioning"
    database_url = (
        '$env:RAYME_DATABASE_URL = '
        '"sqlite+aiosqlite:///C:/Users/pmpg/rayme/RayMe/web-ui/server/data/rayme.sqlite3"'
    )
    migration_marker = 'Write-Host "== Applying web database migrations"'
    migration_command = (
        '& "$repo\\web-ui\\server\\.venv\\Scripts\\python.exe" -m alembic '
        '-c "$repo\\web-ui\\server\\alembic.ini" upgrade head'
    )
    migration_failure = (
        'if ($LASTEXITCODE -ne 0) { throw "Web database migration failed" }'
    )
    launcher_write = 'Write-Host "== Writing scheduled task launchers"'

    assert database_url in source
    assert migration_marker in source
    assert migration_command in source
    assert migration_failure in source
    assert source.index(services_stopped) < source.index(database_url)
    assert source.index(database_url) < source.index(migration_command)
    assert source.index(migration_command) < source.index(launcher_write)


def test_omen_qwen_probe_validates_actual_pep610_source_identity_after_install() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    probe_start = source.index("EXPECTED_RUNTIME_VERSION = \"0.3.2\"")
    probe_end = source.index("import torch", probe_start)
    probe = source[probe_start:probe_end]

    assert source.index("uv sync --project ai-backend --extra tts") < probe_start
    assert 'importlib.metadata.distribution("faster-qwen3-tts")' in probe
    assert 'runtime_distribution.read_text("direct_url.json")' in probe
    assert 'EXPECTED_RUNTIME_REPOSITORY = os.environ["RAYME_QWEN3_RUNTIME_REPOSITORY"]' in probe
    assert 'runtime_source.startswith("git+")' in probe
    assert '.rstrip("/").removesuffix(".git")' in probe
    assert 'runtime_vcs != "git"' in probe
    assert "runtime_commit != EXPECTED_RUNTIME_COMMIT" in probe
