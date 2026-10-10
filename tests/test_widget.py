"""위젯 데이터 처리 테스트 (창·네트워크 없이). 실행: python -m unittest discover -s tests -v"""
import datetime, importlib.machinery, importlib.util, json, os, sys, tempfile, time, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_loader = importlib.machinery.SourceFileLoader("cuw", os.path.join(ROOT, "claude_usage_widget.pyw"))
_spec = importlib.util.spec_from_loader("cuw", _loader)
cuw = importlib.util.module_from_spec(_spec)
_loader.exec_module(cuw)


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


def line(ts, mid, rid, model="claude-opus-5", cwd="C:\\work\\demo", **usage):
    u = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    u.update(usage)
    return json.dumps({"type": "assistant", "timestamp": iso(ts), "requestId": rid, "cwd": cwd,
                       "message": {"id": mid, "model": model, "usage": u}})


class ParseUsage(unittest.TestCase):
    def test_limits_list(self):
        d = {"limits": [
            {"kind": "session", "group": "session", "percent": 42, "severity": "normal",
             "resets_at": "2026-10-10T05:20:00.687+00:00"},
            {"kind": "weekly_all", "group": "weekly", "percent": 80.5},
            {"kind": "weekly_scoped", "group": "weekly", "percent": 10,
             "scope": {"model": {"display_name": "Opus"}}},
            {"kind": "broken"},  # percent 없음 → 무시
        ], "extra_usage": {"is_enabled": True, "used_credits": 1234, "monthly_limit": 5000,
                           "decimal_places": 2, "utilization": 24.68, "currency": "USD"},
           "seven_day_breakdown": {"rows": [{"key": "claude_code", "percent": 90}, {"key": "chat", "percent": 10}]}}
        r = cuw.parse_usage(d)
        self.assertEqual([l["name"] for l in r["limits"]], ["5시간 세션", "주간 한도", "주간 · Opus"])
        self.assertTrue(r["limits"][2]["scoped"])
        utc = datetime.timezone.utc
        self.assertAlmostEqual(r["limits"][0]["resets"],
                               datetime.datetime(2026, 10, 10, 5, 20, 0, 687000, tzinfo=utc).timestamp())
        self.assertEqual(r["extra"]["used"], 12.34)
        self.assertEqual(r["extra"]["limit"], 50.0)
        self.assertEqual([b["name"] for b in r["breakdown"]], ["Claude Code", "채팅"])

    def test_legacy_shape(self):
        r = cuw.parse_usage({"five_hour": {"utilization": 5, "resets_at": "2026-10-10T05:00:00Z"},
                             "seven_day": {"utilization": 50}, "seven_day_opus": None})
        self.assertEqual([l["kind"] for l in r["limits"]], ["session", "weekly_all"])
        self.assertIsNone(r["extra"])

    def test_rejects_unknown(self):
        with self.assertRaises(ValueError):
            cuw.parse_usage({"something": 1})
        with self.assertRaises(ValueError):
            cuw.parse_usage([])


class Models(unittest.TestCase):
    def test_norm_and_name(self):
        self.assertEqual(cuw.norm_model("claude-opus-5-5[1m]"), "claude-opus-5-5")
        self.assertEqual(cuw.norm_model("Claude-Haiku-4-5-20251001"), "claude-haiku-4-5")
        self.assertEqual(cuw.model_name("claude-opus-5-5"), "Opus 5.5")
        self.assertEqual(cuw.model_name("claude-sonnet-5"), "Sonnet 5")
        self.assertEqual(cuw.model_name("gpt-x"), "gpt-x")

    def test_cost(self):
        # [시각, 모델, 프로젝트, 입력, 출력, 캐시쓰기5분, 캐시쓰기1시간, 캐시읽기, fast]
        r = [0, "claude-opus-5", "p", 1_000_000, 1_000_000, 1_000_000, 1_000_000, 1_000_000, 0]
        self.assertAlmostEqual(cuw.cost_of(r), 5 + 25 + 6.25 + 10 + 0.5)
        self.assertAlmostEqual(cuw.cost_of(r[:8] + [1]), 2 * 46.75)
        self.assertIsNone(cuw.cost_of([0, "unknown-model", "p", 1, 1, 0, 0, 0, 0]))

    def test_plan_label(self):
        self.assertEqual(cuw.plan_label("max", "default_claude_max_20x"), "Max 20x")
        self.assertEqual(cuw.plan_label("pro", ""), "Pro")
        # 서버 프로필 형식 (organization_type / rate_limit_tier)
        self.assertEqual(cuw.plan_label("claude_max", "default_claude_max_20x"), "Max 20x")
        self.assertEqual(cuw.plan_label("claude_pro", None), "Pro")


class ScannerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.projects = os.path.join(self.tmp.name, "projects")
        os.makedirs(os.path.join(self.projects, "demo"))
        self.file = os.path.join(self.projects, "demo", "s.jsonl")
        self.patch = mock.patch.multiple(cuw, PROJECTS=self.projects,
                                         CACHE=os.path.join(self.tmp.name, "cache.json"))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def write(self, *lines, mode="a"):
        with open(self.file, mode, encoding="utf-8", newline="\n") as f:
            for l in lines:
                f.write(l + "\n")

    def test_dedup_and_incremental(self):
        now = time.time()
        # 같은 응답이 스트리밍 중에 두 줄로 남음 → 항목별 최댓값 한 번만
        self.write(line(now, "m1", "r1", input_tokens=10, output_tokens=5),
                   line(now, "m1", "r1", input_tokens=10, output_tokens=50, cache_read_input_tokens=100),
                   json.dumps({"type": "user", "message": {"usage": {}}}),
                   line(now, "m2", "r2", model="<synthetic>", output_tokens=999))
        s = cuw.Scanner().scan()
        self.assertEqual(s["today"]["total"], 160)
        self.assertEqual(s["files"], 1)
        self.assertEqual(s["projects"]["today"][0]["name"], "demo")

        # 새로 붙은 줄만 읽고, 캐시에서 다시 만들어도 같은 결과
        self.write(line(now, "m3", "r3", model="claude-haiku-4-5-20251001", input_tokens=40))
        sc = cuw.Scanner()
        self.assertEqual(sc.scan()["today"]["total"], 200)
        self.assertEqual(cuw.Scanner().scan()["today"]["total"], 200)
        self.assertEqual({m["label"] for m in sc.summary()["models"]}, {"Opus 5", "Haiku 4.5"})

    def test_partial_last_line_and_old_records(self):
        now = time.time()
        self.write(line(now - 40 * 86400, "old", "r0", output_tokens=7), line(now, "m1", "r1", output_tokens=3))
        with open(self.file, "a", encoding="utf-8") as f:
            f.write(line(now, "m2", "r2", output_tokens=1000)[:30])  # 아직 쓰는 중인 줄
        self.assertEqual(cuw.Scanner().scan()["today"]["total"], 3)

    def test_unpriced_model_reported(self):
        self.write(line(time.time(), "m1", "r1", model="claude-future-9", output_tokens=1))
        s = cuw.Scanner().scan()
        self.assertEqual(s["unpriced"], ["Future 9"])
        self.assertEqual(s["today"]["cost"], 0)


class PlanNameTest(unittest.TestCase):
    USAGE = {"limits": [{"kind": "session", "percent": 8}]}

    def fetch(self, profile):
        def urlopen(req, timeout=None):
            if req.full_url == cuw.PROFILE_URL:
                if profile is None:
                    raise OSError("down")
                body = profile
            else:
                body = self.USAGE
            r = mock.MagicMock()
            r.__enter__.return_value.read.return_value = json.dumps(body).encode()
            return r
        with mock.patch.object(cuw, "read_credentials", return_value=("tok", {"expires": None, "plan": "Max 5x"})),                 mock.patch.object(cuw.urllib.request, "urlopen", side_effect=urlopen),                 mock.patch.dict(cuw._profile, at=0.0, plan=""):
            return cuw.fetch_plan()

    def test_server_profile_wins_over_stale_credentials(self):
        out = self.fetch({"organization": {"organization_type": "claude_max", "rate_limit_tier": "default_claude_max_20x"}})
        self.assertTrue(out["ok"])
        self.assertEqual(out["plan"], "Max 20x")

    def test_profile_failure_falls_back_to_credentials(self):
        out = self.fetch(None)
        self.assertTrue(out["ok"])
        self.assertEqual(out["plan"], "Max 5x")

    def test_profile_failure_is_not_retried_every_refresh(self):
        with mock.patch.dict(cuw._profile, at=0.0, plan=""),                 mock.patch.object(cuw.urllib.request, "urlopen", side_effect=OSError("down")) as uo:
            self.assertEqual(cuw.profile_plan({}), "")
            self.assertEqual(cuw.profile_plan({}), "")
            self.assertEqual(uo.call_count, 1)


class ApiTest(unittest.TestCase):
    def test_plan_disabled_does_not_touch_credentials(self):
        with mock.patch.object(cuw, "Scanner"), mock.patch.object(cuw, "read_credentials") as rc:
            api = cuw.Api({"plan_enabled": False})
            self.assertEqual(api.plan()["kind"], "disabled")
            rc.assert_not_called()

    def test_set_conf_whitelist(self):
        with mock.patch.object(cuw, "Scanner"), mock.patch.object(cuw, "save_json"):
            conf = {"plan_enabled": False, "interval": 300}
            api = cuw.Api(conf)
            self.assertTrue(api.set_conf("plan_enabled", True))
            self.assertIs(conf["plan_enabled"], True)
            self.assertTrue(api.set_conf("plan_enabled", "yes"))  # 문자열은 켜지 않음
            self.assertIs(conf["plan_enabled"], False)
            self.assertTrue(api.set_conf("interval", 5))
            self.assertEqual(conf["interval"], cuw.MIN_INTERVAL)
            self.assertFalse(api.set_conf("x", 0))
            self.assertFalse(api.set_conf("theme", "neon"))
            self.assertTrue(api.set_conf("collapsed", ["projects", "models", "models"]))
            self.assertEqual(conf["collapsed"], ["models", "projects"])
            self.assertFalse(api.set_conf("collapsed", ["evil"]))
            self.assertFalse(api.set_conf("collapsed", "models"))
            self.assertEqual(conf["collapsed"], ["models", "projects"])

    def test_load_conf_with_bom(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "w.json")
            with open(path, "w", encoding="utf-8-sig") as f:
                json.dump({"plan_enabled": True, "collapsed": ["projects"]}, f)
            with mock.patch.multiple(cuw, CONF=path, LEGACY_CONF=os.path.join(d, "none.json")):
                c = cuw.load_conf()
            self.assertIs(c["plan_enabled"], True)
            self.assertEqual(c["collapsed"], ["projects"])

    def test_load_conf_legacy_and_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            new, old = os.path.join(d, "new.json"), os.path.join(d, "old.json")
            with open(old, "w", encoding="utf-8") as f:
                json.dump({"x": 10, "theme": "dark", "interval": "bad", "evil": 1, "collapsed": ["models", "x"]}, f)
            with mock.patch.multiple(cuw, CONF=new, LEGACY_CONF=old):
                c = cuw.load_conf()
            self.assertEqual((c["x"], c["theme"], c["interval"]), (10, "dark", 300))
            self.assertNotIn("evil", c)
            self.assertIs(c["plan_enabled"], False)
            self.assertEqual(c["collapsed"], ["models"])


if __name__ == "__main__":
    unittest.main()
