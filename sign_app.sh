#!/bin/bash
# (macOS, 선택) build_app.sh로 만든 .app을 Developer ID로 서명하고 Apple 공증(notarization)까지 받는다.
# 공증을 받아야 내려받은 사람이 "확인되지 않은 개발자" 경고 없이 바로 열 수 있다.
# 필요한 환경변수 (CI에서는 같은 이름의 GitHub Secrets):
#   MACOS_CERT_P12_BASE64  Developer ID Application 인증서(.p12)를 base64로
#   MACOS_CERT_PASSWORD    .p12 암호
#   MACOS_SIGN_IDENTITY    예: "Developer ID Application: WENIV Corp. (ABCDE12345)"
#   APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD   공증용 Apple 계정·팀 ID·앱 암호
set -euo pipefail
cd "$(dirname "$0")"

APP="dist/Claude Usage Widget.app"
# 스토어·Release에서 고르기 쉽게 칩 종류를 이름에 적는다 (이름의 "-mac"으로 Mac 파일로 분류됨)
CHIP=$([ "$(uname -m)" = arm64 ] && echo apple-silicon || echo intel)
ZIP="dist/claude_usage_widget-macos-$CHIP.zip"
WORK=$(mktemp -d)
KC="$WORK/sign.keychain-db"
KCPW=$(uuidgen)
trap 'security delete-keychain "$KC" 2>/dev/null || true; rm -rf "$WORK"' EXIT

# 인증서를 임시 키체인에 넣는다 (끝나면 지움)
echo "$MACOS_CERT_P12_BASE64" | base64 --decode > "$WORK/cert.p12"
security create-keychain -p "$KCPW" "$KC"
security set-keychain-settings -lut 3600 "$KC"
security unlock-keychain -p "$KCPW" "$KC"
security import "$WORK/cert.p12" -k "$KC" -P "$MACOS_CERT_PASSWORD" -T /usr/bin/codesign
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KCPW" "$KC" >/dev/null
security list-keychains -d user -s "$KC" $(security list-keychains -d user | tr -d '"')

# 공증에는 hardened runtime이 필요하다. 파이썬(ctypes·pyobjc)이 쓰는 권한만 entitlements.plist에 연다
codesign --force --deep --options runtime --timestamp --entitlements entitlements.plist \
  --sign "$MACOS_SIGN_IDENTITY" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

ditto -c -k --keepParent "$APP" "$WORK/notarize.zip"
xcrun notarytool submit "$WORK/notarize.zip" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
  --password "$APPLE_APP_PASSWORD" --wait
# 공증 직후에는 티켓을 받아 오다 네트워크가 끊겨(Error 68) staple이 실패할 때가 있어 몇 번 다시 한다
for i in 1 2 3 4 5; do
  xcrun stapler staple "$APP" && break
  [ "$i" = 5 ] && exit 1
  sleep 20
done
spctl --assess --type execute --verbose "$APP"

rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"
echo "서명·공증 완료: $ZIP"
