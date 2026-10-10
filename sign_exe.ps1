# (선택) dist\claude_usage_widget.exe에 Azure Artifact Signing으로 코드 서명하기
# 인증은 환경변수로만 받는다: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
# 필요: Windows SDK의 signtool.exe (서명용 dlib는 build\ 아래로 자동 내려받음)
param(
  [string]$File = "$PSScriptRoot\dist\claude_usage_widget.exe",
  [string]$Endpoint = 'https://krc.codesigning.azure.net/',
  [string]$Account = 'wenivsign',
  [string]$CertProfile = 'weniv-public',
  [string]$DlibVersion = '1.0.146'
)
$ErrorActionPreference = 'Stop'
foreach ($v in 'AZURE_TENANT_ID', 'AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET') {
  if (-not [Environment]::GetEnvironmentVariable($v)) { throw "환경변수 $v 가 없습니다." }
}
if (-not (Test-Path -LiteralPath $File)) { throw "서명할 파일이 없습니다: $File" }

$signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
  Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
if (-not $signtool) { throw 'signtool.exe를 찾지 못했습니다. Windows SDK를 설치하세요.' }

$work = "$PSScriptRoot\build\signing"
$dlib = "$work\bin\x64\Azure.CodeSigning.Dlib.dll"
if (-not (Test-Path -LiteralPath $dlib)) {
  New-Item -ItemType Directory -Force $work | Out-Null
  $pkg = "$work\client.zip"
  Invoke-WebRequest "https://api.nuget.org/v3-flatcontainer/microsoft.artifactsigning.client/$DlibVersion/microsoft.artifactsigning.client.$DlibVersion.nupkg" -OutFile $pkg
  Expand-Archive -LiteralPath $pkg -DestinationPath $work -Force
}
$metadata = "$work\metadata.json"
@{ Endpoint = $Endpoint; CodeSigningAccountName = $Account; CertificateProfileName = $CertProfile } |
  ConvertTo-Json | Set-Content -LiteralPath $metadata -Encoding ascii

& $signtool sign /v /debug /fd SHA256 /tr 'http://timestamp.acs.microsoft.com' /td SHA256 `
  /dlib $dlib /dmdf $metadata $File
if ($LASTEXITCODE -ne 0) { throw '서명에 실패했습니다.' }
& $signtool verify /pa $File
if ($LASTEXITCODE -ne 0) { throw '서명 검증에 실패했습니다.' }
Write-Host "서명 완료: $File"
