$ErrorActionPreference = "Stop"

uv sync --dev
uv run pytest
uv run ruff check src tests
uv run basedpyright src tests
uv run pyinstaller --noconfirm --clean ASIntake.spec
Write-Host "Build complete: dist\BistosASIntake.exe"
