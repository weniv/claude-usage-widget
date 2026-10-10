# Claude 사용량 위젯

[![ci](https://github.com/weniv/claude-usage-widget/actions/workflows/ci.yml/badge.svg)](https://github.com/weniv/claude-usage-widget/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Windows 바탕화면에 띄워 두는 작은 창(420px)입니다. **이 PC에서 Claude Code가 쓴 토큰**을 한눈에 보여주고, 원하면 **Claude 플랜 한도가 얼마나 찼는지**도 함께 보여줍니다.

> **비공식 프로젝트입니다.** Anthropic이 만들거나 보증·후원하는 프로그램이 아니며 Anthropic과 관계가 없습니다. "Claude", "Claude Code"는 Anthropic의 상표입니다.

[English summary](#english)

## 보여주는 것

**이 PC의 Claude Code 토큰** (기본으로 켜져 있음, 네트워크를 쓰지 않음)

- 오늘 쓴 토큰(입력·출력·캐시 쓰기·캐시 읽기)
- 최근 7일 날짜별 막대그래프
- 모델별 사용량(7일)
- 프로젝트별 상위 5개(오늘 / 7일 전환). 프로젝트 이름은 작업 폴더 이름입니다.
- **API 환산 추정($)**: 같은 토큰을 Claude API 공개 단가로 썼다면 얼마인지 계산한 **추정치**입니다. 구독 요금과는 관계없습니다. 캐시 쓰기는 5분 TTL에 1.25배, 1시간 TTL에 2배, 빠른 모드는 2배로 계산합니다. 단가표는 `claude_usage_widget.pyw`의 `PRICES`에 있으며, 단가를 모르는 모델은 환산에서 빼고 화면에 따로 알려줍니다.

**플랜 한도** (기본으로 꺼져 있음, [아래](#플랜-한도-켜기-선택) 참고)

| 항목 | 내용 |
|---|---|
| 5시간 세션 | 사용률(%), 초기화 시각, 초기화까지 남은 시간 |
| 주간 한도 | 전체 모델 기준 주간 사용률(%)과 초기화 시각 |
| 모델별 주간 한도 | 모델별 한도가 따로 있을 때만 표시 |
| 추가 사용량 | 추가 사용량(크레딧)이 켜져 있을 때만 사용액 / 월 한도 표시 |
| 주간 사용 비중 | Claude Code·채팅 등 어디서 썼는지 비율 |

막대 색은 서버가 알려주는 심각도(severity)를 따릅니다. 보통은 파랑, 주의는 주황, 위험은 빨강입니다.

## 요구 사항

- Windows 10/11 (Edge WebView2 런타임, 보통 이미 설치되어 있음)
- Claude Code를 이 PC에서 쓰고 있을 것 (`%USERPROFILE%\.claude`)
- 소스로 실행할 때: Python 3.11 이상

macOS·Linux는 지원하지 않습니다(창 고정·단일 실행에 Win32 API를 씁니다).

## 설치와 실행

### exe로 받기

[Releases](https://github.com/weniv/claude-usage-widget/releases)에서 `claude_usage_widget.exe`를 받아 실행합니다. 설치 과정은 없습니다.

- exe는 **WENIV Corp.** 이름으로 코드 서명되어 있습니다(Azure Artifact Signing). 파일 [속성] → [디지털 서명]에서 확인할 수 있고, 같이 올린 `.sha256`으로 해시도 확인할 수 있습니다.
- exe는 태그를 달 때 GitHub Actions(`.github/workflows/release.yml`)가 이 저장소 소스로 빌드하고 서명합니다.

### 소스로 실행

```powershell
pip install -r requirements.txt
pythonw claude_usage_widget.pyw     # 콘솔 창 없이 실행
python  claude_usage_widget.pyw     # 오류를 콘솔에서 보고 싶을 때
```

- 이미 켜져 있으면 새로 띄우지 않고, 켜져 있던 창을 앞으로 가져옵니다.
- 머리의 버튼은 [새로고침], 테마(자동 → 라이트 → 다크), 핀(항상 위)입니다.
- [모델별]·[프로젝트별] 제목을 누르면 목록을 접고 펼 수 있습니다. 접으면 제목 옆에 가장 많이 쓴 항목과 합계만 보이고, 접은 상태는 다음에 켤 때도 이어집니다.
- 모니터를 떼어 내서 저장된 창 위치가 화면 밖이면 기본 위치(주 모니터 오른쪽 위)로 다시 띄웁니다.

### 바탕화면 바로가기

```powershell
powershell -ExecutionPolicy Bypass -File .\make_shortcut.ps1
```

바탕화면에 `Claude 사용량 위젯.lnk`가 생깁니다. 대상은 `pythonw.exe "…\claude_usage_widget.pyw"`이라서 콘솔 창이 뜨지 않습니다.

### exe 직접 빌드

```powershell
pip install -r requirements.txt pyinstaller
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

결과는 `dist\claude_usage_widget.exe`입니다.

서명까지 하려면 `AZURE_TENANT_ID`·`AZURE_CLIENT_ID`·`AZURE_CLIENT_SECRET` 환경변수를 넣고 `sign_exe.ps1`을 실행합니다(Windows SDK의 `signtool.exe` 필요). CI에서는 같은 이름의 GitHub Secrets를 씁니다.

## 플랜 한도 켜기 (선택)

플랜 한도는 Claude Code가 이 PC에 저장해 둔 로그인 토큰으로 `GET https://api.anthropic.com/api/oauth/usage`를 불러 가져옵니다. 이 엔드포인트는 **공개 문서에 없고**, Anthropic은 [OAuth 인증을 Claude Code와 Anthropic 자체 앱의 일반적인 사용을 위한 것](https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use)이라고 안내합니다. 그래서 이 기능은 **기본으로 꺼져 있고**, 위젯의 플랜 한도 카드에서 안내를 읽고 [이해했고, 플랜 한도 켜기]를 눌러야 동작합니다. 카드 제목 줄의 [끄기]로 언제든 다시 끌 수 있습니다.

- 켜지 않아도 [웹에서 보기]로 claude.ai 사용량 페이지를 열어 같은 숫자를 볼 수 있습니다.
- 꺼져 있으면 자격 증명 파일(`.credentials.json`)을 **열지도 않습니다**.
- 엔드포인트는 예고 없이 바뀌거나 막힐 수 있습니다. 위젯은 아는 값만 꺼내고 모르는 값은 무시합니다. 형식이 크게 바뀌면 "응답 형식이 바뀐 것 같습니다"라고 표시되니, 그때는 `parse_usage()`를 고쳐 주세요.
- 켜고 끄는 것은 사용자 본인의 판단입니다. 이 프로젝트는 그 사용에 대해 어떤 보증도 하지 않습니다(LICENSE 참고).

## 데이터는 어디서 오나

| 구분 | 출처 | 언제 |
|---|---|---|
| Claude Code 토큰 | `%USERPROFILE%\.claude\projects\**\*.jsonl`(Claude Code 대화 기록) | 켤 때, [새로고침], 30초마다 |
| 플랜 한도(켰을 때만) | `api/oauth/usage`에 Claude Code 로그인 토큰을 붙여 요청 | 켤 때, [새로고침], 자동 새로고침 간격마다(기본 5분, 최소 1분) |
| 플랜 이름(켰을 때만) | `api/oauth/profile`(같은 토큰). 실패하면 로그인 파일에 적힌 플랜 | 1시간에 한 번 |

- 플랜 이름을 로그인 파일(`.credentials.json`)이 아니라 서버 프로필에서 가져오는 이유: 로그인 파일의 플랜은 로그인할 때 값이라, 그 뒤에 플랜을 바꾸면(예: Max 5x → 20x) 예전 이름이 남습니다.
- Claude Code 설정 폴더를 옮겨 쓰고 있다면(환경 변수 `CLAUDE_CONFIG_DIR`) 그 폴더를 읽습니다.
- jsonl 기록에서 같은 응답이 스트리밍 중에 여러 줄로 남기 때문에 `message.id` + `requestId`로 중복을 걸러 냅니다. 같은 응답의 줄 중에서는 항목별로 가장 큰 값(최종값)을 씁니다.
- 기록 파일은 모두 합치면 수 GB가 될 수 있습니다. 파일마다 어디까지 읽었는지 기억해 두고 **새로 붙은 부분만** 읽습니다. 처음 한 번은 몇 초 걸리고(약 1.8GB 기준 3~4초), 그 뒤로는 0.2초 안팎입니다.

## 저장하는 파일

모두 `%LOCALAPPDATA%\claude-usage-widget\` 아래에 있고, 이 PC 밖으로 나가지 않습니다.

| 파일 | 내용 |
|---|---|
| `widget.json` | 창 위치·크기, 항상 위, 새로고침 간격, 테마, 프로젝트 기간, 접은 목록, 플랜 한도 켜기 |
| `usage_cache.json` | 응답별 토큰 수·모델·작업 폴더 이름·시각(최근 35일), 파일별 읽은 위치. 대화 내용은 저장하지 않음 |
| `webview\` | WebView2 브라우저 데이터 |

예전 버전처럼 스크립트(exe) 옆에 `widget.json`이 있으면 처음 한 번 그 설정을 이어받습니다. 위젯을 지우려면 이 폴더를 지우면 됩니다.

## 보안·개인정보

- **토큰은 이 PC 안에서만 씁니다.** 플랜 한도를 켰을 때 요청할 때마다 파일에서 새로 읽어 `api.anthropic.com`으로 보내는 요청 헤더에만 넣고, 화면(JS)·로그·설정·캐시 어디에도 남기지 않습니다.
- 자격 증명 파일은 **읽기만** 합니다. 토큰을 갱신하거나 파일을 고치지 않습니다. 토큰이 만료되었거나 서버가 401을 돌려주면 "Claude Code를 한 번 실행하면 토큰이 갱신됩니다"라고 안내합니다.
- `api.anthropic.com`(플랜 한도를 켰을 때만) 말고는 어떤 서버에도 접속하지 않습니다. 사용 통계·원격 측정이 없습니다.
- 화면에서 부를 수 있는 기능은 정리된 숫자를 돌려주는 것뿐입니다(`plan`, `local`, `get_conf`, `set_conf`, `open_usage_page`). 파일 내용이나 임의 경로를 돌려주는 기능은 없고, `set_conf`는 정해진 설정 키와 값만 받습니다.
- 화면은 로컬 HTTP 서버 없이 HTML 문자열로 띄웁니다. 그래서 같은 pywebview 방식의 다른 앱과 함께 켜도 포트(42001)가 겹치지 않습니다.
- 보안 문제를 발견하면 공개 이슈 대신 GitHub의 [Security → Report a vulnerability](https://github.com/weniv/claude-usage-widget/security/advisories/new)로 알려 주세요.

## 개발

```powershell
python -m unittest discover -s tests -v
```

테스트는 창·네트워크 없이 응답 파싱, 단가 계산, jsonl 증분 읽기·중복 제거, 설정 검증을 확인합니다. `main`에 push하거나 PR을 열면 GitHub Actions가 Python 3.11·3.13에서 돌립니다.

릴리스: `claude_usage_widget.pyw`의 `VERSION`을 올리고 같은 이름의 태그(`v1.2.3`)를 push하면 exe를 빌드·서명해 Release에 올립니다.

| 파일 | 내용 |
|---|---|
| `claude_usage_widget.pyw` | 데이터 가져오기(플랜 한도·jsonl 집계), 창, JS API |
| `widget.html` | 화면(카드·타일·막대그래프, 다크/라이트) |
| `tests/` | 단위 테스트 |
| `make_shortcut.ps1` | 바탕화면 바로가기 만들기 |
| `build_exe.ps1` | PyInstaller exe 빌드 |
| `sign_exe.ps1` | exe 코드 서명(Azure Artifact Signing) |

## 라이선스

[MIT](LICENSE)

---

## English

**Claude Usage Widget** is a small, unofficial Windows desktop widget (Python + pywebview / Edge WebView2) that shows:

- **Local Claude Code token usage** — today, last 7 days, per model and per project, read incrementally from `~/.claude/projects/**/*.jsonl` (respects `CLAUDE_CONFIG_DIR`). Includes an *estimated* cost at public API prices. No network access.
- **Plan limits (opt-in, off by default)** — 5-hour session and weekly usage from the undocumented `api.anthropic.com/api/oauth/usage` endpoint, using the OAuth token Claude Code already stored locally. Because the endpoint is undocumented and Anthropic states that OAuth authentication is intended for Claude Code and Anthropic's own apps, you must explicitly enable it in the widget. When disabled, the credentials file is never opened. The token is never stored, logged, or passed to the UI.

This project is not affiliated with, endorsed, or sponsored by Anthropic. "Claude" and "Claude Code" are trademarks of Anthropic.

Download the exe from [Releases](https://github.com/weniv/claude-usage-widget/releases), or run from source: `pip install -r requirements.txt` then `pythonw claude_usage_widget.pyw`. Settings and cache live in `%LOCALAPPDATA%\claude-usage-widget\`. The UI is in Korean. Licensed under MIT.
