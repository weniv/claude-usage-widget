#!/bin/bash
# (macOS) PyInstaller로 .app 만들기 — 결과는 dist/Claude Usage Widget.app 과 같은 폴더의 zip (git에 올리지 않음)
# 필요: pip3 install -r requirements.txt pyinstaller
# 실행: ./build_app.sh   (Developer ID 서명·공증은 이어서 ./sign_app.sh)
set -euo pipefail
cd "$(dirname "$0")"

NAME="Claude Usage Widget"
APP="dist/$NAME.app"
VERSION=$(sed -n 's/^VERSION = "\(.*\)"$/\1/p' claude_usage_widget.pyw)
# 스토어·Release에서 고르기 쉽게 칩 종류를 이름에 적는다 (이름의 "-mac"으로 Mac 파일로 분류됨)
CHIP=$([ "$(uname -m)" = arm64 ] && echo apple-silicon || echo intel)
ZIP="dist/claude_usage_widget-macos-$CHIP.zip"

python3 -m PyInstaller --noconfirm --windowed --name "$NAME" \
  --osx-bundle-identifier kr.co.weniv.claude-usage-widget \
  --distpath dist --workpath build --specpath build \
  --add-data "$PWD/widget.html:." \
  --hidden-import webview.platforms.cocoa \
  --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 --exclude-module PySide6 \
  --exclude-module tkinter \
  claude_usage_widget.pyw

# PyInstaller는 버전을 0.0.0으로 적는다. Finder [정보 가져오기]에 맞는 버전이 보이게 고친다
PLIST="$APP/Contents/Info.plist"
for key in CFBundleShortVersionString CFBundleVersion; do
  /usr/libexec/PlistBuddy -c "Set :$key $VERSION" "$PLIST" 2>/dev/null ||
    /usr/libexec/PlistBuddy -c "Add :$key string $VERSION" "$PLIST"
done
/usr/libexec/PlistBuddy -c "Add :LSApplicationCategoryType string public.app-category.developer-tools" "$PLIST" 2>/dev/null || true

# Info.plist를 고치면 서명이 깨지므로 다시 ad-hoc 서명 (Apple Silicon은 서명 없는 앱을 실행하지 않는다)
codesign --force --deep --sign - "$APP"

rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"
echo "완료: $APP ($VERSION) → $ZIP"
