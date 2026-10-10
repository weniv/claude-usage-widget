# (선택) PyInstaller로 exe 한 파일 만들기 — 결과는 dist\claude_usage_widget.exe (git에 올리지 않음)
# 필요: pip install pyinstaller pywebview
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m PyInstaller --noconfirm --onefile --windowed --name claude_usage_widget `
  --distpath dist --workpath build --specpath build `
  --add-data "$PSScriptRoot\widget.html;." `
  --hidden-import webview.platforms.edgechromium --hidden-import webview.platforms.winforms `
  --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 --exclude-module PySide6 `
  claude_usage_widget.pyw
if ($LASTEXITCODE -ne 0) { throw 'exe 빌드에 실패했습니다.' }
Write-Host '완료: dist\claude_usage_widget.exe'
