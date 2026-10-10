# 바탕화면에 'Claude 사용량 위젯' 바로가기를 만든다 (pythonw.exe로 실행해서 콘솔 창이 뜨지 않음)
# 실행: powershell -ExecutionPolicy Bypass -File .\make_shortcut.ps1
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'claude_usage_widget.pyw'
$py = (Get-Command python -ErrorAction Stop).Source
$pyw = Join-Path (Split-Path $py) 'pythonw.exe'
if (-not (Test-Path $pyw)) { throw "pythonw.exe를 찾지 못했습니다: $pyw" }

$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop 'Claude 사용량 위젯.lnk'
$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($lnk)
$s.TargetPath = $pyw
$s.Arguments = '"' + $script + '"'
$s.WorkingDirectory = $PSScriptRoot
$s.Description = 'Claude 플랜 한도와 이 PC의 Claude Code 토큰 사용량'
$s.IconLocation = "$pyw,0"
$s.Save()
Write-Host "바로가기를 만들었습니다: $lnk"
