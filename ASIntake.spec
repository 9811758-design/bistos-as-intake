from pathlib import Path


root = Path(SPECPATH)

a = Analysis(
    [str(root / "as_intake_launcher.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[
        (
            str(root / "src" / "service_validation" / "assets"),
            "service_validation/assets",
        )
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BistosASIntake",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(root / "src" / "service_validation" / "assets" / "bistos_icon.ico"),
)
