from pathlib import Path


def test_single_process_keeps_account_concurrency_limit_global_to_the_container():
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text(encoding="utf-8")

    assert "--workers 1" in dockerfile


def test_restore_scripts_validate_backup_and_reuse_the_persistent_volume():
    root = Path(__file__).parents[2]
    powershell = (root / "scripts" / "restore.ps1").read_text(encoding="utf-8")
    shell = (root / "scripts" / "restore.sh").read_text(encoding="utf-8")

    for script in (powershell, shell):
        assert "quick_check" in script
        assert "stock-analysis-chat-data" in script
        assert "compose" in script
        assert "backend" in script
        assert "health" in script.lower()

    assert "Test-Path -LiteralPath" in powershell
    assert "Resolve-Path -LiteralPath" in powershell
    assert "[ ! -f \"$backup\" ]" in shell
