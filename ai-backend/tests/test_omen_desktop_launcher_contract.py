from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy-omen.sh"
DESKTOP_LAUNCHER = REPO_ROOT / "scripts" / "start-rayme-omen.ps1"
QWEN_MODEL_REVISION = "fd4b254389122332181a7c3db7f27e918eec64e3"


def test_desktop_launcher_matches_the_deployed_qwen_and_service_identity() -> None:
    source = DESKTOP_LAUNCHER.read_text(encoding="utf-8")

    assert f'$qwenModelRevision = "{QWEN_MODEL_REVISION}"' in source
    assert '"RAYME_TTS_DEFAULT_ENGINE" = "qwen3_1_7b"' in source
    assert '"RAYME_QWEN3_MODEL_DIR" = $qwenModelDir' in source
    assert '"RAYME_QWEN3_MODEL_REVISION" = $qwenModelRevision' in source
    assert '"RAYME_DEPLOYED_COMMIT" = $deployedCommit' in source
    assert '"RAYME_AI_BACKEND_SERVICE_TOKEN" = $serviceToken' in source
    assert '"RAYME_AI_BACKEND_CA_BUNDLE" = $aiCaBundle' in source
    assert 'ai-backend-service-token.txt' in source
    assert 'rayme-phase1-rootCA.pem' in source


def test_desktop_launcher_keeps_visible_logs_url_and_close_to_stop() -> None:
    source = DESKTOP_LAUNCHER.read_text(encoding="utf-8")

    assert '$Host.UI.RawUI.WindowTitle = "RayMe Console"' in source
    assert '"[AI]"' not in source  # Prefixes are produced from the AI process name.
    assert '-Name "AI"' in source
    assert '-Name "WEB"' in source
    assert '"Open: $WebUrl"' in source
    assert '"Logs are streaming below. Close this window to stop RayMe."' in source
    assert "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE" in source
    assert "Stop-RayMeChildren" in source
    assert "WindowStyle Hidden" not in source
    assert "WindowStyle Minimized" not in source
    assert "OpenBrowser" not in source


def test_deploy_attests_the_normal_desktop_shortcut_contract() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert f'$qwenModelRevision = "{QWEN_MODEL_REVISION}"' in source
    assert '$shortcutPath = Join-Path $desktopDir "Run RayMe.lnk"' in source
    assert '$shortcutArguments = "-NoProfile -File `"$launcherScript`""' in source
    assert "$shortcut.Arguments = $shortcutArguments" in source
    assert "$shortcut.WindowStyle = 1" in source
    assert "visible AI and Web logs; close the console to stop" in source
    assert "$verifiedShortcut.TargetPath" in source
    assert "$verifiedShortcut.Arguments" in source
    assert "$verifiedShortcut.WorkingDirectory" in source
    assert "$verifiedShortcut.WindowStyle" in source
    assert "$verifiedShortcut.Description" in source
    assert "Desktop launcher verification failed" in source
