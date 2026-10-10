"""
Claude 사용량 위젯 (비공식, Anthropic과 관계없음) — 바탕화면 바로가기로 실행 (창 없이 pythonw)

화면은 widget.html (Edge WebView2, pywebview). 필요 패키지: pip install -r requirements.txt

  - 플랜 한도 (기본 꺼짐, 화면에서 직접 켜야 함): Claude Code가 저장해 둔 로그인 토큰
    (~/.claude/.credentials.json)으로 https://api.anthropic.com/api/oauth/usage 를 읽는다
    (5시간 세션·주간·모델별 주간·추가 사용량). 공개 문서에 없는 엔드포인트라 기본은 끄고,
    사용자가 안내를 읽고 켰을 때만 처음 켤 때·[새로고침]·자동 새로고침 간격(기본 5분, 최소 1분)마다 가져온다.
    토큰은 가져올 때마다 새로 읽고, 어디에도 저장·기록하지 않으며 화면(JS)으로도 넘기지 않는다.
    자격 증명 파일은 읽기만 한다 (갱신·수정하지 않음).
  - 이 PC의 Claude Code 토큰: ~/.claude/projects/**/*.jsonl 의 응답 기록을 모아
    오늘·최근 7일·모델별·프로젝트별로 보여준다. 파일마다 읽은 위치를 기억해 새로 붙은 부분만 읽는다.
    (캐시: %LOCALAPPDATA%\\claude-usage-widget\\usage_cache.json)
  - Claude Code 설정 폴더를 옮겼다면(환경 변수 CLAUDE_CONFIG_DIR) 그 폴더를 쓴다.

창 위치·크기, 항상 위, 새로고침 간격, 테마, 플랜 한도 켜기는 %LOCALAPPDATA%\\claude-usage-widget\\widget.json에
저장한다 (예전 위치인 스크립트·exe 옆 widget.json이 있으면 처음 한 번 이어받는다).
"""
import datetime, glob, json, ntpath, os, re, socket, sys, threading, time, urllib.error, urllib.request

VERSION = "1.1.0"
FROZEN = getattr(sys, "frozen", False)
BASE = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
ASSETS = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or BASE, "claude-usage-widget")
CONF = os.path.join(DATA_DIR, "widget.json")
LEGACY_CONF = os.path.join(BASE, "widget.json")  # 예전 저장 위치 (스크립트·exe 옆)
CACHE = os.path.join(DATA_DIR, "usage_cache.json")
CLAUDE_DIR = os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join("~", ".claude"))
CREDENTIALS = os.path.join(CLAUDE_DIR, ".credentials.json")
PROJECTS = os.path.join(CLAUDE_DIR, "projects")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"  # 공개 문서에 없는 엔드포인트라 바뀔 수 있다
PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"  # 플랜 이름용 (역시 공개 문서에 없음)
PROFILE_TTL = 3600        # 플랜은 자주 바뀌지 않으니 프로필은 1시간에 한 번만 묻는다
TITLE = "Claude 사용량"
RETAIN_DAYS = 35          # 이보다 오래된 응답 기록은 캐시에 두지 않는다
MIN_INTERVAL = 60         # 자동 새로고침 최소 간격(초)
MAX_INTERVAL = 3600
FOLDS = ("models", "projects")  # 접을 수 있는 목록
AUTH_MSG = "Claude Code를 한 번 실행하면 토큰이 갱신됩니다"


def load_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:  # 메모장·PowerShell로 고치면 BOM이 붙는다
            return json.load(f)
    except Exception:
        return default


_save_lock = threading.Lock()


def save_json(path, data):
    with _save_lock:  # JS 호출은 스레드마다 따로 들어와서 동시에 쓰지 않도록
        tmp = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, path)
        except OSError:
            pass


def iso_ts(s):
    """'2026-10-10T05:20:00.687+00:00' / '...Z' → epoch 초 (실패하면 None)"""
    if not isinstance(s, str) or not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# ---------------------------------------------------------------- 플랜 한도 (OAuth usage)
def plan_label(sub, tier):
    sub, tier = (sub or "").lower().removeprefix("claude_"), (tier or "").lower()
    m = re.search(r"max_(\d+)x", tier)
    if sub == "max" or m:
        return "Max" + (f" {m.group(1)}x" if m else "")
    return {"pro": "Pro", "team": "Team", "enterprise": "Enterprise", "free": "Free"}.get(sub, sub.title() or "")


_profile = {"at": 0.0, "plan": ""}


def profile_plan(headers):
    """서버에 저장된 지금 플랜. 로그인 파일의 플랜은 로그인할 때 값이라 그 뒤에 플랜을 바꾸면 예전 값으로 남는다.
    실패하면 ""를 돌려준다."""
    if time.time() - _profile["at"] < PROFILE_TTL:
        return _profile["plan"]
    try:
        with urllib.request.urlopen(urllib.request.Request(PROFILE_URL, headers=headers), timeout=10) as r:
            org = (json.loads(r.read().decode("utf-8")) or {}).get("organization") or {}
        plan = plan_label(org.get("organization_type"), org.get("rate_limit_tier"))
    except Exception:  # 실패하면 10분 뒤에 다시 묻는다 (오프라인일 때 새로고침마다 기다리지 않게)
        _profile.update(at=time.time() - PROFILE_TTL + 600, plan="")
        return ""
    _profile.update(at=time.time(), plan=plan)
    return plan


def read_credentials():
    """(토큰, 메타) — 토큰은 호출한 함수 안에서만 쓰고 버린다. 파일은 읽기만 한다."""
    with open(CREDENTIALS, encoding="utf-8") as f:
        o = (json.load(f) or {}).get("claudeAiOauth") or {}
    meta = {"expires": num(o.get("expiresAt")), "plan": plan_label(o.get("subscriptionType"), o.get("rateLimitTier"))}
    return o.get("accessToken"), meta


LIMIT_NAMES = {"session": "5시간 세션", "weekly_all": "주간 한도"}
BREAKDOWN_NAMES = {"claude_code": "Claude Code", "chat": "채팅", "cowork": "Cowork", "other": "기타"}


def parse_usage(d):
    """응답은 문서화되지 않아서 아는 키만 조심스럽게 꺼낸다 (모르는 키는 무시)"""
    if not isinstance(d, dict):
        raise ValueError("응답이 객체가 아님")
    limits = []
    for it in d.get("limits") or []:
        if not isinstance(it, dict) or num(it.get("percent")) is None:
            continue
        kind = str(it.get("kind") or "")
        scope = it.get("scope") if isinstance(it.get("scope"), dict) else {}
        model = scope.get("model") if isinstance(scope.get("model"), dict) else {}
        scoped = model.get("display_name") or model.get("id")
        if kind in LIMIT_NAMES:
            name = LIMIT_NAMES[kind]
        elif scoped:
            name = f"주간 · {scoped}" if it.get("group") == "weekly" or "weekly" in kind else str(scoped)
        else:
            name = kind.replace("_", " ") or "한도"
        limits.append({"kind": kind, "group": str(it.get("group") or ""), "name": name,
                       "percent": num(it.get("percent")), "severity": str(it.get("severity") or ""),
                       "resets": iso_ts(it.get("resets_at")), "scoped": bool(scoped)})
    if not limits:  # limits 목록이 없을 때: 예전 형식(five_hour/seven_day...)으로
        for key, kind, group, name in (("five_hour", "session", "session", LIMIT_NAMES["session"]),
                                       ("seven_day", "weekly_all", "weekly", LIMIT_NAMES["weekly_all"]),
                                       ("seven_day_opus", "weekly_scoped", "weekly", "주간 · Opus"),
                                       ("seven_day_sonnet", "weekly_scoped", "weekly", "주간 · Sonnet")):
            w = d.get(key)
            if isinstance(w, dict) and num(w.get("utilization")) is not None:
                limits.append({"kind": kind, "group": group, "name": name, "percent": num(w["utilization"]),
                               "severity": "", "resets": iso_ts(w.get("resets_at")),
                               "scoped": kind == "weekly_scoped"})
    if not limits:
        raise ValueError("한도 정보가 없음")

    extra = None
    e = d.get("extra_usage")
    if isinstance(e, dict) and e.get("is_enabled") is True:
        dp = int(num(e.get("decimal_places")) or 0)
        scale = 10 ** dp
        extra = {"used": (num(e.get("used_credits")) or 0) / scale,
                 "limit": (num(e.get("monthly_limit")) / scale) if num(e.get("monthly_limit")) is not None else None,
                 "percent": num(e.get("utilization")), "currency": str(e.get("currency") or "USD")}

    breakdown = []
    b = d.get("seven_day_breakdown")
    if isinstance(b, dict):
        for r in b.get("rows") or []:
            if isinstance(r, dict) and num(r.get("percent")) is not None:
                key = str(r.get("key") or "")
                breakdown.append({"name": BREAKDOWN_NAMES.get(key) or str(r.get("display_name") or key),
                                  "percent": num(r["percent"])})
    return {"limits": limits, "extra": extra, "breakdown": breakdown}


def fetch_plan():
    """화면에 넘길 정리된 결과만 돌려준다. 토큰·원본 응답·파일 경로는 넣지 않는다."""
    out = {"ok": False, "fetched": time.time(), "plan": ""}
    try:
        token, meta = read_credentials()
    except FileNotFoundError:
        out.update(kind="auth", error="Claude Code 로그인 정보가 없습니다. Claude Code에서 로그인하세요")
        return out
    except Exception:
        out.update(kind="auth", error="로그인 정보 파일을 읽지 못했습니다")
        return out
    out["plan"] = meta["plan"]
    if not token:
        out.update(kind="auth", error=AUTH_MSG)
        return out
    if meta["expires"] and meta["expires"] / 1000 < time.time():
        out.update(kind="auth", error="토큰이 만료되었습니다. " + AUTH_MSG)
        return out
    headers = {"Authorization": "Bearer " + token, "anthropic-beta": "oauth-2025-04-20",
               "Accept": "application/json", "User-Agent": f"claude-usage-widget/{VERSION}"}
    del token
    out["plan"] = profile_plan(headers) or meta["plan"]
    req = urllib.request.Request(USAGE_URL, headers=headers)
    headers = None
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        code = e.code
        if code == 401:
            out.update(kind="auth", error=AUTH_MSG)
        elif code == 429:
            out.update(kind="http", error="요청이 너무 잦아 잠시 막혔습니다 (HTTP 429). 잠시 뒤 다시 시도하세요")
        else:
            out.update(kind="http", error=f"서버가 오류로 응답했습니다 (HTTP {code})")
        return out
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, socket.gaierror):
            detail = "주소를 찾지 못했습니다. 인터넷 연결을 확인하세요"
        elif isinstance(reason, (TimeoutError, socket.timeout)):
            detail = "응답 시간이 초과되었습니다"
        elif isinstance(reason, ConnectionError):
            detail = "연결이 거부되었거나 끊겼습니다"
        else:
            detail = type(reason).__name__
        out.update(kind="network", error="네트워크에 연결하지 못했습니다", detail=detail)
        return out
    except ValueError:
        out.update(kind="parse", error="응답을 해석하지 못했습니다")
        return out
    finally:
        req = None  # 헤더(토큰)를 담은 요청 객체를 바로 놓아 준다
    try:
        out.update(parse_usage(body))
    except Exception:
        out.update(kind="parse", error="응답 형식이 바뀐 것 같습니다 (위젯 업데이트 필요)")
        return out
    out["ok"] = True
    return out


# ---------------------------------------------------------------- 이 PC의 Claude Code 토큰 (jsonl)
# API 환산 추정용 단가 (USD / 100만 토큰): 입력, 출력, 캐시 읽기. 캐시 쓰기는 5분 1.25배·1시간 2배.
PRICES = {
    "claude-fable-5-1": (10, 50, 0.25), "claude-mythos-5-1": (10, 50, 0.25),
    "claude-fable-5": (10, 50, 1.0), "claude-mythos-5": (10, 50, 1.0),
    "claude-opus-5-5": (4, 20, 0.20), "claude-opus-5": (5, 25, 0.50),
    "claude-opus-4-8": (5, 25, 0.50), "claude-opus-4-7": (5, 25, 0.50),
    "claude-opus-4-6": (5, 25, 0.50), "claude-opus-4-5": (5, 25, 0.50),
    "claude-opus-4-1": (15, 75, 1.50), "claude-opus-4": (15, 75, 1.50),
    "claude-sonnet-5": (2, 10, 0.20), "claude-sonnet-4-6": (3, 15, 0.30),
    "claude-sonnet-4-5": (3, 15, 0.30), "claude-sonnet-4": (3, 15, 0.30),
    "claude-haiku-4-5": (1, 5, 0.10),
}


def norm_model(m):
    """'claude-opus-5-5[1m]' → 'claude-opus-5-5', 'claude-haiku-4-5-20251001' → 'claude-haiku-4-5'"""
    m = re.sub(r"\[.*?\]$", "", str(m or "").strip().lower())
    return re.sub(r"-\d{8}$", "", m)


def model_name(m):
    x = re.match(r"claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?$", m)
    if x:
        return f"{x.group(1).title()} {x.group(2)}{'.' + x.group(3) if x.group(3) else ''}"
    return m or "알 수 없음"


def cost_of(r):
    """레코드 → API 환산 비용(USD). 단가를 모르는 모델은 None"""
    p = PRICES.get(r[1])
    if not p:
        return None
    pin, pout, pcr = p
    c = (r[3] * pin + r[4] * pout + r[5] * pin * 1.25 + r[6] * pin * 2 + r[7] * pcr) / 1e6
    return c * (2 if r[8] else 1)  # 빠른 모드(fast)는 2배


class Scanner:
    """파일별로 읽은 위치를 기억해 새로 붙은 줄만 읽는다.
    레코드: 키(message.id + requestId) → [시각, 모델, 프로젝트, 입력, 출력, 캐시쓰기5분, 캐시쓰기1시간, 캐시읽기, fast]
    스트리밍 중에 같은 응답이 여러 줄로 기록되므로(출력 토큰이 점점 커짐) 키마다 항목별 최댓값을 쓴다."""

    VERSION = 1

    def __init__(self):
        self.lock = threading.Lock()
        c = load_json(CACHE, {})
        if c.get("v") != self.VERSION:
            c = {}
        self.files = c.get("files", {})   # 경로 → [읽은 바이트 위치, 파일 크기]
        self.recs = c.get("recs", {})
        self.last = None

    def _line(self, line, cutoff):
        try:
            d = json.loads(line)
        except ValueError:
            return False
        if not isinstance(d, dict) or d.get("type") != "assistant":
            return False
        m = d.get("message")
        if not isinstance(m, dict) or not isinstance(m.get("usage"), dict):
            return False
        model = norm_model(m.get("model"))
        if not model or model.startswith("<"):  # <synthetic> 등 실제 호출이 아닌 기록
            return False
        ts = iso_ts(d.get("timestamp"))
        if ts is None or ts < cutoff:
            return False
        u = m["usage"]
        cw = int(num(u.get("cache_creation_input_tokens")) or 0)
        cc = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
        cw1h = min(cw, int(num(cc.get("ephemeral_1h_input_tokens")) or 0))
        vals = [int(num(u.get("input_tokens")) or 0), int(num(u.get("output_tokens")) or 0),
                cw - cw1h, cw1h, int(num(u.get("cache_read_input_tokens")) or 0)]
        mid, rid = m.get("id"), d.get("requestId")
        key = f"{mid}|{rid}" if mid or rid else "u|" + str(d.get("uuid"))
        cwd = d.get("cwd") or ""
        project = ntpath.basename(cwd.rstrip("\\/")) or cwd or "?"
        fast = 1 if u.get("speed") == "fast" else 0
        old = self.recs.get(key)
        if old is None:
            self.recs[key] = [round(ts), model, project] + vals + [fast]
            return True
        new = old[:3] + [max(a, b) for a, b in zip(old[3:8], vals)] + [old[8] or fast]
        if new != old:
            self.recs[key] = new
            return True
        return False

    def scan(self):
        with self.lock:
            t0 = time.time()
            cutoff = t0 - RETAIN_DAYS * 86400
            changed, seen = False, set()
            for p in glob.glob(os.path.join(PROJECTS, "**", "*.jsonl"), recursive=True):
                seen.add(p)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                pos, size = self.files.get(p, [0, 0])
                if st.st_size == size and pos == size:
                    continue
                if p not in self.files and st.st_mtime < cutoff:  # 오래된 파일은 읽지 않고 끝으로 표시
                    self.files[p] = [st.st_size, st.st_size]
                    changed = True
                    continue
                if st.st_size < pos:  # 파일이 새로 쓰였으면 처음부터 (같은 키는 중복으로 세지 않음)
                    pos = 0
                try:
                    with open(p, "rb") as f:
                        f.seek(pos)
                        chunk = f.read(st.st_size - pos)
                except OSError:
                    continue
                end = chunk.rfind(b"\n") + 1  # 아직 쓰는 중인 마지막 줄은 다음에 읽는다
                for line in chunk[:end].splitlines():
                    if b'"usage"' in line and b'"assistant"' in line and self._line(line, cutoff):
                        changed = True
                self.files[p] = [pos + end, st.st_size]
                changed = True
            for p in [p for p in self.files if p not in seen]:  # 지워진 파일
                del self.files[p]
                changed = True
            old = [k for k, r in self.recs.items() if r[0] < cutoff]
            for k in old:
                del self.recs[k]
            if changed or old:
                save_json(CACHE, {"v": self.VERSION, "files": self.files, "recs": self.recs})
            self.last = {"scanned": time.time(), "took": round(time.time() - t0, 2), "files": len(seen)}
            return self.summary()

    def summary(self):
        today = datetime.date.today()
        days = [today - datetime.timedelta(days=i) for i in range(6, -1, -1)]
        idx = {d.isoformat(): i for i, d in enumerate(days)}
        z = lambda: {"in": 0, "out": 0, "cw": 0, "cr": 0, "total": 0, "cost": 0.0}
        per_day = [z() for _ in days]
        models, proj_today, proj_week, unknown = {}, {}, {}, set()

        def add(a, r, c):
            a["in"] += r[3]; a["out"] += r[4]; a["cw"] += r[5] + r[6]; a["cr"] += r[7]
            a["total"] += r[3] + r[4] + r[5] + r[6] + r[7]
            a["cost"] += c or 0.0

        for r in self.recs.values():
            i = idx.get(datetime.date.fromtimestamp(r[0]).isoformat())
            if i is None:
                continue
            c = cost_of(r)
            if c is None:
                unknown.add(r[1])
            add(per_day[i], r, c)
            add(models.setdefault(r[1], z()), r, c)
            add(proj_week.setdefault(r[2], z()), r, c)
            if i == 6:
                add(proj_today.setdefault(r[2], z()), r, c)

        def top(d, n):
            rows = sorted(d.items(), key=lambda kv: -kv[1]["total"])
            out = [{"name": k, **v} for k, v in rows[:n]]
            if len(rows) > n:
                rest = z()
                for _, v in rows[n:]:
                    for k in rest:
                        rest[k] += v[k]
                out.append({"name": f"그 밖의 {len(rows) - n}개", "rest": True, "count": len(rows) - n, **rest})
            return out

        for i, d in enumerate(days):
            per_day[i].update(date=d.isoformat(), label=f"{d.month}/{d.day}", wd="월화수목금토일"[d.weekday()])
        model_rows = top(models, 5)
        for m in model_rows:
            m["label"] = m["name"] if m.get("rest") else model_name(m["name"])
        return {**(self.last or {}), "today": per_day[-1], "days": per_day, "models": model_rows,
                "projects": {"today": top(proj_today, 5), "week": top(proj_week, 5)},
                "unpriced": sorted(model_name(m) for m in unknown)}


# ---------------------------------------------------------------- 항상 위 (UI 스레드에서)
def set_topmost(window, on):
    """pywebview 6.2.1의 window.on_top = x 는 JS API 작업 스레드에서 form.TopMost를 직접 바꿔서
    (WinForms 스레드 간 호출) 창이 멈춘다. UI 스레드로 넘기고 기다리지 않는다(BeginInvoke)."""
    try:
        from webview.platforms.winforms import BrowserView
        from System import Func, Type
    except Exception:
        return False
    form = BrowserView.instances.get(window.uid)
    if form is None:
        return False

    def apply():
        form.TopMost = bool(on)

    form.BeginInvoke(Func[Type](apply))
    return True


# ---------------------------------------------------------------- JS에서 부르는 API
class Api:
    """화면에 넘기는 것은 정리된 숫자와 이름뿐이다. 파일 내용·경로를 돌려주는 메서드는 두지 않는다."""

    def __init__(self, conf):
        self._conf = conf
        self._window = None
        self._scanner = Scanner()
        self._plan_lock = threading.Lock()
        self._plan, self._plan_at = None, 0.0

    def plan(self):
        if not self._conf.get("plan_enabled"):  # 꺼져 있으면 자격 증명 파일을 열지도 않는다
            return {"ok": False, "fetched": time.time(), "kind": "disabled", "plan": ""}
        # 이미 가져오는 중이면 끝날 때까지 기다렸다가 그 결과를 같이 받는다 (일찍 돌아가지 않음)
        with self._plan_lock:
            if self._plan is not None and time.time() - self._plan_at < 3:
                return self._plan
            try:
                res = fetch_plan()
            except Exception as e:  # 예상 못 한 오류도 화면에는 종류만
                res = {"ok": False, "fetched": time.time(), "kind": "internal",
                       "error": f"내부 오류 ({type(e).__name__})"}
            self._plan, self._plan_at = res, time.time()
            return res

    def local(self):
        try:
            return self._scanner.scan()
        except Exception as e:
            return {"error": f"기록을 읽지 못했습니다 ({type(e).__name__})"}

    def get_conf(self):
        c = {k: self._conf.get(k) for k in ("topmost", "interval", "proj_range", "theme", "plan_enabled", "collapsed")}
        c["version"] = VERSION
        return c

    def set_conf(self, key, value):
        if key == "topmost":
            self._conf["topmost"] = bool(value)
            if self._window:
                set_topmost(self._window, self._conf["topmost"])
        elif key == "interval":
            try:
                self._conf["interval"] = max(MIN_INTERVAL, min(MAX_INTERVAL, int(value)))
            except (TypeError, ValueError):
                return False
        elif key == "plan_enabled":
            self._conf["plan_enabled"] = value is True
            with self._plan_lock:
                self._plan = None  # 껐다 켜면 예전 결과를 쓰지 않고 새로 가져온다
        elif key == "proj_range" and value in ("today", "week"):
            self._conf["proj_range"] = value
        elif key == "theme" and value in ("auto", "light", "dark"):
            self._conf["theme"] = value
        elif key == "collapsed" and isinstance(value, list) and all(v in FOLDS for v in value):
            self._conf["collapsed"] = sorted(set(value))
        else:
            return False
        save_json(CONF, self._conf)
        return True

    def open_usage_page(self):
        import webbrowser
        webbrowser.open("https://claude.ai/settings/usage")


def single_instance():
    """이미 떠 있으면 그 창을 앞으로 가져오고 False"""
    try:
        import ctypes
        k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
        k32.CreateMutexW.restype = ctypes.c_void_p
        u32.FindWindowW.restype = ctypes.c_void_p
        u32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        u32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        single_instance.mutex = k32.CreateMutexW(None, False, "Local\\claude-usage-widget")
        if k32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            h = u32.FindWindowW(None, TITLE)
            if h:
                u32.ShowWindow(h, 9)  # SW_RESTORE
                u32.SetForegroundWindow(h)
            return False
    except Exception:
        pass
    return True


def load_conf():
    conf = {"x": None, "y": None, "w": 420, "h": 900, "topmost": True, "interval": 300,
            "proj_range": "today", "theme": "auto", "plan_enabled": False, "collapsed": []}
    saved = load_json(CONF, None)
    if saved is None:
        saved = load_json(LEGACY_CONF, {})
    if isinstance(saved, dict):
        conf.update({k: v for k, v in saved.items() if k in conf})
    try:
        conf["interval"] = max(MIN_INTERVAL, min(MAX_INTERVAL, int(conf["interval"])))
    except (TypeError, ValueError):
        conf["interval"] = 300
    conf["plan_enabled"] = conf["plan_enabled"] is True
    c = conf["collapsed"]
    conf["collapsed"] = sorted({v for v in c if v in FOLDS}) if isinstance(c, list) else []
    return conf


def on_screen(x, y):
    """저장된 창 위치(왼쪽 위 근처)가 지금 연결된 모니터 안에 있는지. 확인하지 못하면 True"""
    try:
        import ctypes, ctypes.wintypes as wt
        u32 = ctypes.windll.user32
        u32.MonitorFromPoint.restype = ctypes.c_void_p
        u32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
        return bool(u32.MonitorFromPoint(wt.POINT(int(x) + 40, int(y) + 10), 0))  # MONITOR_DEFAULTTONULL
    except Exception:
        return True


def create_window(conf, api):
    import webview
    if conf["x"] is not None and not on_screen(conf["x"], conf["y"]):  # 모니터를 떼어 냈으면 기본 자리로
        conf["x"] = conf["y"] = None
    if conf["x"] is None:  # 처음엔 주 모니터 작업 영역 오른쪽 위
        try:
            import ctypes, ctypes.wintypes as wt
            wa = wt.RECT()
            ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(wa), 0)  # SPI_GETWORKAREA
            conf["x"], conf["y"] = max(wa.left, wa.right - conf["w"] - 16), wa.top + 16
            conf["h"] = min(conf["h"], wa.bottom - wa.top - 32)
        except Exception:
            pass
    # 파일 경로 대신 HTML 문자열로 띄운다. private_mode=False 이면 pywebview가 로컬 파일을
    # 고정 포트(127.0.0.1:42001)의 내장 HTTP 서버로 내보내는데, 같은 방식의 다른 pywebview 앱과
    # 동시에 켜면 포트가 겹쳐 남의 화면이 뜬다. 문자열로 넘기면 HTTP 서버를 아예 쓰지 않는다.
    with open(os.path.join(ASSETS, "widget.html"), encoding="utf-8") as f:
        page = f.read()
    win = webview.create_window(TITLE, html=page, js_api=api,
                                width=conf["w"], height=conf["h"], x=conf["x"], y=conf["y"],
                                min_size=(360, 420), on_top=conf["topmost"], background_color="#16181d")
    api._window = win

    def moved(x, y):
        conf["x"], conf["y"] = x, y

    def resized(w, h):
        conf["w"], conf["h"] = w, h

    win.events.moved += moved
    win.events.resized += resized
    win.events.closing += lambda: save_json(CONF, conf)
    return win


def main():
    if not single_instance():
        return
    import webview
    conf = load_conf()
    api = Api(conf)
    create_window(conf, api)
    webview.start(private_mode=False, storage_path=os.path.join(DATA_DIR, "webview"))


if __name__ == "__main__":
    main()
