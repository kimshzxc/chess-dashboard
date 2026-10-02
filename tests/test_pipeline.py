"""스모크 테스트: 통계·추이·퍼즐·알림 흐름이 엔진 없이 작은 합성 DB 에서 끝까지 도는지, 통계 함수가 알려진 값을 내는지.
실행: python -m unittest discover -s tests -v"""
import json, os, sys, tempfile, unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pipeline  # noqa: E402

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
LINE = dict(best_line=[dict(san="d4", uci="d2d4", fen="x")], refutation=[dict(san="e5", uci="e7e5", fen="y")],
            alts=[dict(san="Nf3", uci="g1f3")], puzzle_ok=True)


def fake_plies(my_color, blunder):
    """2수짜리 가짜 게임. 내 수의 손실을 blunder 로 조절한다."""
    w_mine = 1 if my_color == "w" else 0
    loss_w, loss_b = (blunder, 0) if w_mine else (0, blunder)
    wp = lambda l: round(max(0.0, pipeline.winpct(0) - pipeline.winpct(-l)), 1)
    return [
        dict(ply=1, move=1, mover="w", mine=w_mine, san="e4", best="d4", is_best=0, cp_before=0, cp_after=-loss_w, loss=loss_w,
             wp_loss=wp(loss_w), clock=590.0, spent=10.0, capture=0, chk=0, piece=1, phase="opening", fen=START),
        dict(ply=2, move=1, mover="b", mine=1 - w_mine, san="e5", best="c5", is_best=0, cp_before=0, cp_after=-loss_b, loss=loss_b,
             wp_loss=wp(loss_b), clock=580.0, spent=20.0, capture=0, chk=0, piece=1, phase="opening", fen=AFTER_E4),
    ]


class StatsHelpers(unittest.TestCase):
    def test_known_values(self):
        self.assertAlmostEqual(pipeline.t_pvalue(2.0, 30), 0.0546, places=3)
        self.assertAlmostEqual(pipeline.prop_p(10, 100, 20, 100), 0.0477, places=3)
        self.assertEqual(pipeline.welch_p([1, 2, 3], [1, 2, 3]), 1.0)
        rho, p = pipeline.spearman(list(range(20)), list(range(20)))
        self.assertAlmostEqual(rho, 1.0)

    def test_trend_statuses(self):
        mk = lambda vals: [dict(d=f"2026-01-{i % 28 + 1:02d}", v=v, n=1) for i, v in enumerate(vals)]
        self.assertEqual(pipeline.trend_analysis(mk([1] * 5), "hung")["status"], "insufficient")
        t = pipeline.trend_analysis(mk([3] * 60 + [0] * 30), "hung")
        self.assertEqual(t["status"], "better"); self.assertTrue(t["improved"]); self.assertEqual(t["k"], 30)
        t = pipeline.trend_analysis(mk([1, 0] * 45), "hung")
        self.assertEqual(t["status"], "flat")

    def test_evidence(self):
        # 8판 3점 vs 나머지 50%: 우연 범위 → 근거 부족
        weak = pipeline.evidence([1, 1, 1, 0, 0, 0, 0, 0], [1, 0] * 60)
        self.assertFalse(weak["confident"]); self.assertEqual(weak["n"], 8)
        # 60판 20% vs 나머지 55%: 뚜렷함
        strong = pipeline.evidence([1] * 12 + [0] * 48, [1] * 110 + [0] * 90)
        self.assertTrue(strong["confident"])
        self.assertFalse(pipeline.evidence([1], [1, 0, 1])["confident"])          # 표본 1개
        self.assertTrue(pipeline.evidence_one([60, 80, 120, 90, 150, 70])["confident"])
        self.assertFalse(pipeline.evidence_one([60, -80, 120, -90, 15, -70])["confident"])


class WithDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        pipeline.DATA = self.tmp.name
        pipeline.DOCS = os.path.join(self.tmp.name, "docs")
        pipeline.DB_PATH = os.path.join(self.tmp.name, "chess.db")
        os.makedirs(pipeline.DOCS)
        self.con = pipeline.db()
        self.base = base = int(datetime(2026, 9, 21, 12, 0, tzinfo=pipeline.KST).timestamp())   # 월요일
        for i in range(24):
            color = "w" if i % 2 == 0 else "b"
            outcome = "L" if i % 3 == 0 else "W"
            url = f"https://www.chess.com/game/live/{1000 + i}"
            end = base + (i // 6) * 86400 + (i % 6) * 600      # 6판씩 같은 세션(10분 간격), 세션 사이는 하루
            self.con.execute("INSERT INTO games(url,end_time,date,my_color,white,black,welo,belo,opp,opp_elo,my_elo,result,outcome,my_result,"
                             "opp_result,termination,eco,eco_name,time_control,pgn,notified) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
                             (url, end, datetime.fromtimestamp(end, pipeline.KST).strftime("%Y-%m-%d"), color, "me" if color == "w" else "opp",
                              "opp" if color == "w" else "me", 900, 900, "opp", 900, 900 + i, "1-0", outcome,
                              "win" if outcome == "W" else "resigned", "resigned" if outcome == "W" else "win", "x", "C20", "Kings Pawn", "600", ""))
            pipeline.store_analysis(self.con, url, fake_plies(color, 400 if i % 4 == 0 else 20))

    def tearDown(self):
        self.con.close(); self.tmp.cleanup()

    def add_lines(self, **over):
        for fen, san, best in pipeline.lines_todo(self.con):
            self.con.execute("INSERT OR REPLACE INTO lines(fen,played,best,data) VALUES(?,?,?,?)", (fen, san, best, json.dumps(dict(LINE, **over))))
        self.con.commit()

    def test_stats_end_to_end(self):
        S = pipeline.compute_stats(pipeline.load_games(self.con), self.con)
        self.assertEqual(S["overview"]["games"], 24)
        for k in ("time", "phase", "conversion", "tactics", "openings", "monthly", "recent", "worst", "examples", "tilt", "rating_series", "weaknesses"):
            self.assertIn(k, S)
        self.assertEqual(len(S["rating_series"]), 24)
        self.assertEqual(S["tilt"]["sessions"]["n"], 4)
        self.assertEqual(S["tilt"]["sessions"]["max_len"], 6)
        for w in S["weaknesses"]:
            self.assertIn(w["key"], pipeline.METRICS)
            self.assertIn(w["level"], ("critical", "serious", "warning", "good", "hint"))
            self.assertIn(w["trend"]["status"], ("insufficient", "better", "maybe_better", "flat", "maybe_worse", "worse"))
            if w["level"] == "hint":
                self.assertFalse(w["ev"]["confident"])
        hints = [w["level"] == "hint" for w in S["weaknesses"]]
        self.assertEqual(hints, sorted(hints))            # 근거 약한 항목은 뒤에 모인다
        json.dumps(S, ensure_ascii=False)                 # 직렬화 가능해야 한다

    def test_metric_series_all_keys(self):
        games = pipeline.load_games(self.con)
        for key in pipeline.METRICS:
            arg = ["w", "e4 e5"] if key == "opening" else None
            self.assertIsInstance(pipeline.metric_series(games, key, arg), list)

    def test_lines_and_puzzles(self):
        todo = pipeline.lines_todo(self.con)
        self.assertTrue(todo)
        self.assertEqual(len(todo), len(set(todo)))
        self.assertEqual(pipeline.export_puzzles(self.con), 0)        # 수순 계산 전에는 퍼즐이 없다
        self.add_lines()
        self.assertEqual(pipeline.lines_todo(self.con), [])
        n = pipeline.export_puzzles(self.con)
        self.assertGreater(n, 0)
        pz = json.load(open(os.path.join(pipeline.DOCS, "puzzles.json")))
        for k in ("id", "fen", "uci", "best_uci", "wp_loss", "after_fen", "alts", "legal", "best_line"):
            self.assertIn(k, pz[0])
        self.assertIn(pz[0]["best_uci"][:4], pz[0]["legal"].split())
        self.assertEqual(pz[0]["alts"][0]["uci"], "g1f3")
        self.add_lines_not_ok()
        self.assertEqual(pipeline.export_puzzles(self.con), 0)        # 좋은 수가 너무 많은 국면은 퍼즐에서 뺀다

    def add_lines_not_ok(self):
        self.con.execute("DELETE FROM lines"); self.add_lines(puzzle_ok=False)

    def test_cached_lines_fallback(self):
        self.con.execute("CREATE TABLE pv_cache(fen TEXT, played TEXT, data TEXT, PRIMARY KEY(fen, played))")
        old = dict(best_line=[dict(san="c4", uci="c2c4", fen="x")], refutation=[dict(san="e5", uci="e7e5", fen="y")])
        self.con.execute("INSERT INTO pv_cache VALUES(?,?,?)", (START, "e4", json.dumps(old)))
        got = pipeline.cached_lines(self.con, START, "e4", "d4")
        self.assertEqual(got["best_line"], [])                        # 첫 수(c4)가 최선(d4)과 달라 숨김
        self.assertEqual(len(got["refutation"]), 1)
        self.assertEqual(len(pipeline.cached_lines(self.con, START, "e4", "c4")["best_line"]), 1)
        self.con.execute("INSERT INTO lines VALUES(?,?,?,?)", (START, "e4", "d4", json.dumps(LINE)))
        self.assertEqual(pipeline.cached_lines(self.con, START, "e4", "d4")["best_line"][0]["san"], "d4")

    def test_reanalysis_queue(self):
        self.con.execute("UPDATE games SET depth=14 WHERE url LIKE '%1000'")
        redo = self.con.execute("SELECT COUNT(*) FROM games WHERE analyzed=1 AND (depth IS NULL OR depth!=?)", (pipeline.DEPTH,)).fetchone()[0]
        self.assertEqual(redo, 1)

    def test_notify_queue_waits_for_deploy(self):
        calls = []
        orig = (pipeline.wait_for_page, pipeline.notify)
        pipeline.wait_for_page = lambda url, timeout=150, every=5: calls.append(("wait", url)) or True
        pipeline.notify = lambda cfg, game, summary, base: calls.append(("notify", game["url"]))
        try:
            url = "https://www.chess.com/game/live/1003"
            pipeline.queue_save([url, "https://www.chess.com/game/live/does-not-exist"])
            self.assertTrue(os.path.exists(pipeline.queue_path()))
            sent = pipeline.send_queued(self.con, dict(GITHUB_OWNER="o", GITHUB_REPO="r"))
        finally:
            pipeline.wait_for_page, pipeline.notify = orig
        self.assertEqual(sent, 1)
        self.assertEqual(calls, [("wait", "https://o.github.io/r/games/1003.json"), ("notify", url)])   # 배포 확인이 알림보다 먼저
        self.assertFalse(os.path.exists(pipeline.queue_path()))
        self.assertEqual(pipeline.queue_load(), [])

    def test_weekly(self):
        now = datetime(2026, 9, 28, 9, 30, tzinfo=pipeline.KST)        # 다음 주 월요일 09:30
        title, body = pipeline.weekly_message(self.con, now)
        self.assertIn("주간 요약 9/21~9/27", title)
        self.assertIn("24판 16승 0무 8패", body)
        sent = []
        orig = pipeline.send_ntfy
        pipeline.send_ntfy = lambda cfg, title, message, **kw: sent.append(title) or True
        try:
            cfg = dict(GITHUB_OWNER="o", GITHUB_REPO="r")
            self.assertFalse(pipeline.maybe_weekly(self.con, cfg, datetime(2026, 9, 25, 10, 0, tzinfo=pipeline.KST)))   # 처음 켠 주는 건너뜀
            self.assertFalse(pipeline.maybe_weekly(self.con, cfg, datetime(2026, 9, 28, 8, 0, tzinfo=pipeline.KST)))    # 월요일 9시 전
            self.assertTrue(pipeline.maybe_weekly(self.con, cfg, now))
            self.assertFalse(pipeline.maybe_weekly(self.con, cfg, datetime(2026, 9, 29, 9, 0, tzinfo=pipeline.KST)))    # 같은 주에 한 번만
        finally:
            pipeline.send_ntfy = orig
        self.assertEqual(len(sent), 1)
        self.assertIsNone(pipeline.weekly_message(self.con, datetime(2026, 11, 2, 10, 0, tzinfo=pipeline.KST)))        # 게임 없는 주


if __name__ == "__main__":
    unittest.main()
