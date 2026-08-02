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


def test_omen_deploy_preflights_phase1_tls_before_teardown_and_token_rotation() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    path_assignments = (
        '$raymeStateRoot = Split-Path -Parent $repo',
        '$phase1TlsDir = Join-Path $raymeStateRoot "phase1-tls"',
        '$aiCaBundle = Join-Path $phase1TlsDir "rayme-phase1-rootCA.pem"',
        '$aiTlsCert = Join-Path $phase1TlsDir "rayme.local+1.pem"',
        '$aiTlsKey = Join-Path $phase1TlsDir "rayme.local+1-key.pem"',
        '$serviceTokenPath = Join-Path $raymeStateRoot "ai-backend-service-token.txt"',
    )
    for assignment in path_assignments:
        assert source.count(assignment) == 1

    checkout_validation = 'throw "OMEN checkout is $actualHead, expected $expectedHead"'
    tls_gate = 'foreach ($tlsPath in @($aiTlsCert, $aiTlsKey, $aiCaBundle)) {'
    leaf_validation = 'Test-Path -LiteralPath $tlsPath -PathType Leaf'
    optional_voxcpm_stop = "if ($verifyVoxCpm2) {\n  Stop-RayMePortOwners"
    canonical_qwen_stop = "Stop-RayMePortOwners\nInvoke-RayMeQwen3Provisioning"
    final_service_stop = "Stop-RayMePortOwners\n\nfunction Protect-Phase09QwenLogs"
    launcher_write = 'Write-Host "== Writing scheduled task launchers"'
    task_delete = "schtasks /Delete /TN RayMePhase1AI"
    task_register = "Register-RayMeTask -TaskName RayMePhase1AI"
    token_rotation = "RandomNumberGenerator"

    gate_index = source.index(tls_gate)
    leaf_index = source.index(leaf_validation)
    assert source.index(checkout_validation) < gate_index < leaf_index
    for destructive_or_write_marker in (
        "function Stop-RayMePortOwners",
        optional_voxcpm_stop,
        canonical_qwen_stop,
        final_service_stop,
        launcher_write,
        task_delete,
        task_register,
    ):
        assert leaf_index < source.index(destructive_or_write_marker)

    assert "RandomNumberGenerator" in source
    assert source.count('set "RAYME_AI_BACKEND_SERVICE_TOKEN=%%T"') == 2
    assert source.count('for /f "usebackq delims=" %%T in ("$serviceTokenPath")') == 2
    assert source.count("--cert $aiTlsCert --key $aiTlsKey") == 2
    assert 'set "RAYME_AI_BACKEND_BASE_URL=https://192.168.1.199:9443"' in source
    assert "icacls.exe $serviceTokenPath /inheritance:r" in source
    assert 'set "RAYME_AI_BACKEND_CA_BUNDLE=$aiCaBundle"' in source
    assert 'AppData\\Local\\mkcert\\rootCA.pem' not in source
    assert source.index(canonical_qwen_stop) < source.index(token_rotation)
    assert source.index(token_rotation) < source.index(launcher_write)
    assert "curl.exe --cacert $aiCaBundle" in source
    assert "curl.exe -k" not in source


def test_omen_deploy_verifies_rotated_credential_through_web_and_fails_mismatch() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    readiness = "https://192.168.1.199:8443/api/ai-backend/readiness"

    assert readiness in source
    readiness_call = source[source.index(readiness) - 80 : source.index(readiness) + 180]
    assert "curl.exe --fail --cacert $aiCaBundle" in readiness_call
    assert "could not authenticate with the rotated AI backend credential" in source
    assert '$webCredentialReadiness.authenticated -ne $true' in source


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
