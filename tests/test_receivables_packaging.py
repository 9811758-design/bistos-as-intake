from pathlib import Path


def test_receivables_build_stops_when_a_native_gate_fails() -> None:
    script = Path("build_receivables.ps1").read_text(encoding="utf-8")

    assert "function Invoke-Checked" in script
    assert sum(line.startswith("Invoke-Checked {") for line in script.splitlines()) == 5


def test_receivables_package_includes_outlook_timezone_support() -> None:
    # Given
    spec = Path("ReceivablesReconciliation.spec").read_text(encoding="utf-8")

    # When
    hidden_import_is_present = '"win32timezone"' in spec

    # Then
    assert hidden_import_is_present
