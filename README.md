# Claude 사용량 위젯

Windows 바탕화면에 띄워 두는 작은 창(420px)입니다. **Claude 플랜 한도가 얼마나 찼는지**와 **이 PC에서 Claude Code가 쓴 토큰**을 한눈에 보여줍니다.

Python 3.13 + [pywebview](https://pywebview.flowrl.com/) 6.2.1(Edge WebView2)로 만들었고, 화면은 `widget.html` 한 파일입니다.

## 보여주는 것

**플랜 한도**: claude.ai 계정 기준이며, 웹의 "사용량" 페이지와 같은 숫자입니다.

| 항목 | 내용 |
|---|---|
| 5시간 세션 | 사용률(%), 초기화 시각, 초기화까지 남은 시간 |
| 주간 한도 | 전체 모델 기준 주간 사용률(%)과 초기화 시각 |
| 모델별 주간 한도 | Opus·Sonnet·Fable처럼 모델별 한도가 따로 있을 때만 표시 |
| 추가 사용량 | 추가 사용량(크레딧)이 켜져 있을 때만 사용액 / 월 한도 표시 |
| 주간 사용 비중 | Claude Code·채팅 등 어디서 썼는지 비율 |

막대 색은 서버가 알려주는 심각도(severity)를 따릅니다. 보통은 파랑, 주의는 주황, 위험은 빨강입니다.

**이 PC의 Claude Code 토큰**은 이 PC에 남은 Claude Code 기록만으로 계산합니다.

- 오늘 쓴 토큰(입력·출력·캐시 쓰기·캐시 읽기)
- 최근 7일 날짜별 막대그래프
- 모델별 사용량(7일)
- 프로젝트별 상위 5개(오늘 / 7일 전환). 프로젝트 이름은 작업 폴더 이름입니다.
- **API 환산 추정($)**: 같은 토큰을 Claude API 공개 단가로 썼다면 얼마인지 계산한 **추정치**입니다. 구독 요금과는 관계없습니다. 캐시 쓰기는 5분 TTL에 1.25배, 1시간 TTL에 2배, 빠른 모드는 2배로 계산합니다. 단가표는 `claude_usage_widget.pyw`의 `PRICES`에 있으며, 단가를 모르는 모델은 환산에서 빼고 화면에 따로 알려줍니다.

## 데이터는 어디서 오나

| 구분 | 출처 | 언제 |
|---|---|---|
| 플랜 한도 | `GET https://api.anthropic.com/api/oauth/usage`에 Claude Code 로그인 토큰을 붙여 요청 | 켤 때, [새로고침] 누를 때, 자동 새로고침 간격마다(기본 5분, 최소 1분, 아래쪽에서 변경) |
| Claude Code 토큰 | `%USERPROFILE%\.claude\projects\**\*.jsonl`(Claude Code 대화 기록) | 켤 때, [새로고침], 30초마다 |

- 토큰은 `%USERPROFILE%\.claude\.credentials.json`의 `claudeAiOauth.accessToken`을 씁니다. Claude Code에 로그인되어 있으면 따로 설정할 것이 없습니다.
- jsonl 기록에서 같은 응답이 스트리밍 중에 여러 줄로 남기 때문에 `message.id` + `requestId`로 중복을 걸러 냅니다. 같은 응답의 줄 중에서는 항목별로 가장 큰 값(최종값)을 씁니다.
- 기록 파일은 모두 합치면 수 GB가 될 수 있습니다. 파일마다 어디까지 읽었는지 기억해 두고 **새로 붙은 부분만** 읽습니다. 처음 한 번은 몇 초 걸리고(약 1.8GB 기준 3~4초), 그 뒤로는 0.2초 안팎입니다.
  캐시 위치: `%LOCALAPPDATA%\claude-usage-widget\usage_cache.json`(최근 35일 치만 보관)

## 보안 메모

- **토큰은 이 PC 안에서만 씁니다.** 요청할 때마다 파일에서 새로 읽어 `api.anthropic.com`으로 보내는 요청 헤더에만 넣고, 화면(JS)·로그·설정·캐시 어디에도 남기지 않습니다.
- 자격 증명 파일은 **읽기만** 합니다. 토큰을 갱신하거나 파일을 고치지 않습니다. 토큰이 만료되었거나 서버가 401을 돌려주면 "Claude Code를 한 번 실행하면 토큰이 갱신됩니다"라고 안내합니다. Claude Code를 실행하면 Claude Code가 직접 토큰을 갱신합니다.
- 화면에서 부를 수 있는 기능은 정리된 숫자를 돌려주는 것뿐입니다(`plan`, `local`, `get_conf`, `set_conf`, `open_usage_page`). 파일 내용이나 임의 경로를 돌려주는 기능은 없고, `set_conf`는 정해진 설정 키만 받습니다.
- 화면은 로컬 HTTP 서버 없이 HTML 문자열로 띄웁니다. 그래서 같은 pywebview 방식의 다른 위젯과 함께 켜도 포트(42001)가 겹치지 않습니다.
- **주의**: `api/oauth/usage`는 **공개 문서에 없는 엔드포인트**라 예고 없이 바뀌거나 막힐 수 있습니다. 위젯은 아는 값만 꺼내고 모르는 값은 무시하도록 만들었습니다. 형식이 크게 바뀌면 "응답 형식이 바뀐 것 같습니다"라고 표시되니, 그때는 `parse_usage()`를 고쳐 주세요.

## 설치

```powershell
pip install pywebview
```

Windows 10/11에는 보통 Edge WebView2 런타임이 이미 설치되어 있습니다.

## 실행

```powershell
pythonw claude_usage_widget.pyw     # 콘솔 창 없이 실행
python  claude_usage_widget.pyw     # 오류를 콘솔에서 보고 싶을 때
```

- 이미 켜져 있으면 새로 띄우지 않고, 켜져 있던 창을 앞으로 가져옵니다.
- 머리의 버튼은 [새로고침], 테마(자동 → 라이트 → 다크), 핀(항상 위)입니다.
- 창 위치·크기, 항상 위, 새로고침 간격, 테마, 프로젝트 기간은 스크립트 옆 `widget.json`에 저장됩니다(git에는 올라가지 않음).

## 바탕화면 바로가기

```powershell
powershell -ExecutionPolicy Bypass -File .\make_shortcut.ps1
```

바탕화면에 `Claude 사용량 위젯.lnk`가 생깁니다. 대상은 `pythonw.exe "…\claude_usage_widget.pyw"`이라서 콘솔 창이 뜨지 않습니다.

## (선택) exe로 만들기

```powershell
pip install pyinstaller
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

결과는 `dist\claude_usage_widget.exe`이고 `build\`, `dist\`, `*.exe`는 git에 올리지 않습니다. exe로 실행하면 `widget.json`이 exe 옆에 저장됩니다.

## 파일

| 파일 | 내용 |
|---|---|
| `claude_usage_widget.pyw` | 데이터 가져오기(플랜 한도·jsonl 집계), 창, JS API |
| `widget.html` | 화면(카드·타일·막대그래프, 다크/라이트) |
| `make_shortcut.ps1` | 바탕화면 바로가기 만들기 |
| `build_exe.ps1` | (선택) PyInstaller exe 빌드 |
