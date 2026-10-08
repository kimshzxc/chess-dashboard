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


class MistakeTypes(unittest.TestCase):
    """실수 유형 분류: 알려진 국면에서 기대한 유형이 나오는지."""
    E4E5 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    HANGING_B = "r1bqk2r/pppp1ppp/2n5/2bNp3/4P1n1/3PBN2/PPP2PPP/R2QKB1R b KQkq - 0 6"     # 흑 c5 비숍이 e3 비숍에 걸려 있다

    def ply(self, fen, san, best, before=0, after=-400, phase="middlegame"):
        return dict(fen=fen, san=san, best=best, cp_before=before, cp_after=after, loss=max(0, before - after), phase=phase,
                    mine=1, wp_loss=round(pipeline.winpct(before) - pipeline.winpct(after), 1))

    def test_categories(self):
        cat = pipeline.mistake_cat
        self.assertEqual(cat(self.ply(self.E4E5, "Ba6", "Nf3"), dict(best="Nxa6")), "into_capture")
        self.assertEqual(cat(self.ply(self.HANGING_B, "O-O", "Bxe3"), dict(best="Bxc5")), "ignored_threat")
        self.assertEqual(cat(self.ply(self.HANGING_B, "d6", "Bxe3", after=-200), dict(best="h3")), "missed_capture")
        self.assertEqual(cat(self.ply(self.E4E5, "Nf3", "Qh5", before=9990, after=300), None), "missed_mate")
        self.assertEqual(cat(self.ply(self.E4E5, "g4", "Nf3", before=0, after=-9980), dict(best="Qh4")), "allowed_mate")
        self.assertEqual(cat(self.ply(self.E4E5, "a3", "Nf3", after=-120, phase="opening"), dict(best="Nf6")), "opening")
        for k in ("into_capture", "ignored_threat", "missed_capture", "missed_mate", "allowed_mate", "opening"):
            self.assertIn(k, pipeline.CAT_KEYS)

    def test_only_real_mistakes_are_tagged(self):
        small = dict(self.ply(self.E4E5, "a3", "Nf3", after=-30), ply=3)
        big = dict(self.ply(self.E4E5, "Ba6", "Nf3"), ply=3)
        self.assertNotIn("cat", pipeline.tag_mistakes([small])[0])
        self.assertEqual(pipeline.tag_mistakes([big, dict(mine=0, wp_loss=0, best="Nxa6", san="Nxa6")])[0]["cat"], "into_capture")


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
        co = S["coach"]
        self.assertEqual(co["n"], sum(c["n"] for c in co["cats"]))
        self.assertEqual(co["n"], 6)                      # 24판 중 4판마다 한 번 400 손해
        self.assertAlmostEqual(sum(c["share"] for c in co["cats"]), 100, delta=0.5)
        self.assertEqual([c["cost"] for c in co["cats"]], sorted((c["cost"] for c in co["cats"]), reverse=True))
        for c in co["cats"]:
            self.assertIn(c["key"], pipeline.CAT_KEYS)
            self.assertEqual(len(c["recent"]["seq"]), co["k"])
            self.assertEqual(c["recent"]["games"], sum(1 for x in c["recent"]["seq"] if x))
            self.assertTrue(c["examples"] and all(e["cat"] == c["key"] for e in c["examples"]))
        self.assertTrue(set(co["focus"]) <= {c["key"] for c in co["cats"]})
        for col in "wb":
            R = S["repertoire"][col]
            self.assertEqual(R["base"]["n"], 12)
            for side in ("mine", "opp"):
                self.assertEqual(sum(r["n"] for r in R[side]), 12)            # 모든 판이 한 묶음에만 들어간다
                for r in R[side]:
                    self.assertEqual(r["win"] + r["draw"] + r["loss"], r["n"])
                    self.assertIn(r["verdict"], ("weak", "weak_hint", "strong", "strong_hint", "even"))
                    self.assertAlmostEqual(r["diff"], r["score"] - R["base"]["score"], places=1)
            self.assertEqual(R["mine"][0]["key"], "1.e4" if col == "w" else "1…e5")
        for col in "wb":
            for o in S["openings"][col]:
                self.assertEqual(sum(o["mist"]["by_move"]), o["mist"]["n"])
                self.assertEqual(sum(c["n"] for c in o["mist"]["cats"]), o["mist"]["n"])
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
        for k in ("id", "fen", "uci", "best_uci", "wp_loss", "after_fen", "alts", "legal", "best_line", "cat"):
            self.assertIn(k, pz[0])
        self.assertIn(pz[0]["best_uci"][:4], pz[0]["legal"].split())
        self.assertEqual(pz[0]["alts"][0]["uci"], "g1f3")
        self.add_lines_not_ok()
        self.assertEqual(pipeline.export_puzzles(self.con), 0)        # 좋은 수가 너무 많은 국면은 퍼즐에서 뺀다

    def add_lines_not_ok(self):
        self.con.execute("DELETE FROM lines"); self.add_lines(puzzle_ok=False)

    def test_game_export_and_coach_file(self):
        self.assertEqual(pipeline.export_missing_games(self.con), 24)
        g = json.load(open(os.path.join(pipeline.DOCS, "games", "1000.json")))
        self.assertEqual([p.get("cat") for p in g["plies"]], ["opening", None])       # 내 수(백)의 400 손해만 유형이 붙는다
        self.assertEqual(pipeline.export_missing_games(self.con), 0)                  # 형식 버전이 같으면 다시 내보내지 않는다
        pipeline.meta_set(self.con, "game_export_v", "old")
        self.assertEqual(pipeline.export_missing_games(self.con), 24)
        pipeline.render_all(self.con, dict(CHESSCOM_USERNAME="me"))
        coach = json.load(open(os.path.join(pipeline.DOCS, "coach.json")))
        stats = json.load(open(os.path.join(pipeline.DOCS, "stats.json")))["windows"]["all"]["coach"]
        self.assertEqual(coach["focus"], stats["focus"])
        self.assertEqual(set(coach["cats"]), {c["key"] for c in stats["cats"]})

    def test_book_cache_and_budget(self):
        import chess

        class Eng:                                     # 엔진 대역: 합법 수 앞의 3개를 차례로 돌려준다
            calls = 0

            def analyse(self, b, limit, multipv=1):
                Eng.calls += 1
                out = []
                for i, m in enumerate(list(b.legal_moves)[:multipv]):
                    b2 = b.copy(); b2.push(m)
                    out.append(dict(pv=[m, next(iter(b2.legal_moves))], score=chess.engine.PovScore(chess.engine.Cp(30 - 10 * i), b.turn)))
                return out
        budget = [1]
        ev = pipeline.book_eval(self.con, START, Eng(), budget)
        self.assertEqual((len(ev), budget[0], ev[0]["cp"]), (3, 0, 30))
        self.assertTrue(ev[0]["reply"])
        self.assertIsNone(pipeline.book_eval(self.con, AFTER_E4, Eng(), budget))          # 예산이 없으면 계산하지 않는다
        self.assertEqual(pipeline.book_eval(self.con, START, None, [0]), ev)              # 캐시에서
        self.assertEqual(Eng.calls, 1)
        self.assertEqual(pipeline.build_book(self.con, pipeline.load_games(self.con)), ({}, 0, 0))   # 2수짜리 가짜 게임에는 만들 오프닝이 없다
        from collections import defaultdict
        key = ("e4", "Nf3", "Bc4")
        short, _, done = pipeline.book_line(self.con, None, [0], "w", key, True, {}, {})
        self.assertFalse(done); self.assertEqual([p["san"] for p in short], ["e4"])        # 엔진 없이는 캐시가 끝나는 데서 멈춘다
        plies, branches, done = pipeline.book_line(self.con, Eng(), [1000], "w", key, True, {}, {})
        self.assertTrue(done); self.assertEqual(branches, [])
        self.assertEqual(sum(p["mine"] for p in plies), pipeline.EARLY_MOVES)
        self.assertEqual([p["san"] for p in plies if p["mine"]][:3], list(key))
        b = chess.Board()
        for p in plies:                                                                   # 라인의 수는 모두 둘 수 있는 수이고 fen 이 이어진다
            b.push_uci(p["uci"]); self.assertEqual(b.fen(), p["fen"])
        again, _, done = pipeline.book_line(self.con, None, [0], "w", key, True, {}, {})
        self.assertTrue(done); self.assertEqual(again, plies)                              # 다시 만들 때는 캐시만으로

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
