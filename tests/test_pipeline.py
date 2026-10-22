"""스모크 테스트: 통계·추이·퍼즐·알림 흐름이 엔진 없이 작은 합성 DB 에서 끝까지 도는지, 통계 함수가 알려진 값을 내는지.
실행: python -m unittest discover -s tests -v"""
import json, os, sys, tempfile, unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chess  # noqa: E402
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
        self.assertEqual(cat(self.ply(self.HANGING_B, "d6", "Bxe3", before=300, after=0), dict(best="h3")), "missed_capture")
        self.assertEqual(cat(self.ply(self.E4E5, "Nf3", "Qh5", before=9990, after=300), None), "missed_mate")
        self.assertEqual(cat(self.ply(self.E4E5, "g4", "Nf3", before=0, after=-9980), dict(best="Qh4")), "allowed_mate")
        self.assertEqual(cat(self.ply(self.E4E5, "a3", "Nf3", after=-120, phase="opening"), dict(best="Nf6")), "opening")
        for k in ("into_capture", "ignored_threat", "missed_capture", "missed_mate", "allowed_mate", "opening"):
            self.assertIn(k, pipeline.CAT_KEYS)

    def test_exchange_based_rules(self):
        """내준 유형은 그 칸의 교환이 실제로 손해일 때만, 놓친 유형은 얻을 것이 있었을 때만 붙는다 (실제 게임에서 잘못 분류되던 국면들)."""
        cat = pipeline.mistake_cat
        # 비숍끼리 맞바꾼 것뿐: 손해 보는 교환이 아니라 더 좋은 조용한 수(f6)를 놓친 판단 실수
        even = "2rr2k1/1p2ppbp/p5q1/4B1p1/3P4/8/PPbQ1PPP/R1N1R1K1 b - - 3 19"
        self.assertEqual(cat(self.ply(even, "Bxe5", "f6", before=393, after=15), dict(best="Rxe5")), "middlegame")
        # 룩으로 폰을 잡고 룩을 잃음: 진짜 손해 교환
        self.assertEqual(cat(self.ply("8/1pR5/1r6/4k3/8/6K1/6P1/8 w - - 4 52", "Rxb7", "Kh4", before=0, after=-593), dict(best="Rxb7")), "bad_trade")
        # 킹을 b 줄로 옮겨 퀸이 핀에 걸리면서 c5 비숍의 수비가 사라짐: 두기 전에는 걸려 있지 않았다
        pin = "2kr4/p1p2p1p/2p2p2/2b1p3/1qP1Pr2/1N5Q/P4P1K/1RR5 b - - 2 21"
        self.assertEqual(cat(self.ply(pin, "Kb8", "f5", before=633, after=-765), dict(best="Nxc5")), "unguard")
        # 같은 값의 잡기(Nxc6)로 시작해 c5 비숍을 얻는 수법: 걸린 기물을 둔 것이 아니라 상대의 다음 수를 못 본 것
        combo = "r1bqk2r/pppp1ppp/2n2n2/2b5/3NP3/2N1B3/PPP2PPP/R2QKB1R b KQkq - 2 6"
        self.assertEqual(cat(self.ply(combo, "O-O", "Bb6", before=0, after=-650), dict(best="Nxc6")), "allowed_deep")
        # 최선이 잡는 수여도 형세를 지키기만 하는 맞교환이면 '안 잡음'이 아니다
        self.assertEqual(cat(self.ply(self.HANGING_B, "d6", "Bxe3", before=0, after=-180), dict(best="h3")), "middlegame")
        b = chess.Board(self.E4E5)
        self.assertEqual(pipeline.see(chess.Board("8/1pR5/1r6/4k3/8/6K1/6P1/8 w - - 4 52"), chess.Move.from_uci("c7b7")), -4)
        self.assertEqual(pipeline.see(chess.Board(even), chess.Move.from_uci("g7e5")), 0)

    def test_tactic_kinds(self):
        """'상대의 다음 수를 못 봄'은 응수의 성격으로 여섯 가지로 나뉜다 (실제 게임 국면)."""
        cat = pipeline.mistake_cat
        # Nxf7 이 d6 퀸과 h8 룩을 동시에 노림
        self.assertEqual(cat(self.ply("2kr1b1r/ppp2ppp/1q3n2/4Nb2/1P1n4/P1NPB3/2P1BPPP/R2Q1RK1 b - - 0 11", "Qd6", "Nxe2+", before=-230, after=-664), dict(best="Nxf7")), "allowed_fork")
        # Bb8+ 가 f4 킹 뒤의 g3 룩을 꿴다 (체크 스큐어)
        self.assertEqual(cat(self.ply("5b2/B6p/8/1K2kp2/2P1p3/1P4rP/P5P1/3R4 b - - 8 35", "Kf4", "Ke6", before=-235, after=-855), dict(best="Bb8+")), "allowed_pin")
        # Rh2+ 체크 뒤에 a2 룩을 잃는다 (꿰는 줄은 없다)
        self.assertEqual(cat(self.ply("8/8/6p1/2p3k1/8/3PK3/r4PR1/8 b - - 3 55", "Kh5", "Kf5", before=-1, after=-711), dict(best="Rh2+")), "allowed_check")
        # 조용한 Qc6 가 외통을 위협한다
        self.assertEqual(cat(self.ply("r1b1qrk1/ppp2ppp/8/5n2/2B1N2n/P1Q1B3/2P2PPP/3R1RK1 w - - 8 16", "Ng3", "Nc5", before=-6, after=-571), dict(best="Qc6")), "allowed_check")
        # c3 가 b4 나이트 하나를 쫓는데 갈 곳이 없다
        self.assertEqual(cat(self.ply("r2qkb1r/ppp2ppp/4pn2/3p4/1n1P1B2/1Q2PN2/PPP2PPP/RN3RK1 b kq - 3 8", "Be7", "Qc8", before=-68, after=-413), dict(best="c3")), "allowed_attack")
        # e5 폰을 공짜로 잡히고 그 나이트가 더 노린다
        self.assertEqual(cat(self.ply("r1bqkb1r/ppp2ppp/2n5/1B1pp3/4n3/3P1N2/PPP1QPPP/RNB2RK1 b kq - 0 6", "Nf6", "Nd6", before=-168, after=-369), dict(best="Nxe5")), "allowed_pawn")
        # 조용한 Rfe8 뒤에 b7 의 퀸이 갇힌다
        self.assertEqual(cat(self.ply("r4rk1/pp2bpp1/7p/3QpP2/q1p5/2P1B3/1P4PP/2KR3R w - - 0 21", "Qxb7", "Qd7", before=-14, after=-664), dict(best="Rfe8")), "allowed_deep")
        for k in pipeline.TACTIC_KEYS:
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
        for k in ("time", "phase", "conversion", "tactics", "openings", "monthly", "recent", "worst", "examples", "tilt", "rating_series", "weaknesses", "log"):
            self.assertIn(k, S)
        self.assertEqual(len(S["rating_series"]), 24)
        self.assertEqual(len(S["log"]), 24)
        self.assertEqual(sum(sum(x["c"].values()) for x in S["log"]), S["coach"]["n"])     # 판별 기록의 실수 수는 유형 집계와 같다
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
            self.assertEqual(sum(r["n"] for r in R["rows"]), 12)             # 모든 판이 한 묶음에만 들어간다
            for r in R["rows"]:
                self.assertEqual(r["win"] + r["draw"] + r["loss"], r["n"])
                self.assertIn(r["verdict"], ("weak", "weak_hint", "strong", "strong_hint", "even"))
                self.assertAlmostEqual(r["diff"], r["score"] - R["base"]["score"], places=1)
                self.assertEqual(sum(r["mist"]["by_move"]), r["mist"]["n"])
                self.assertEqual(sum(c["n"] for c in r["mist"]["cats"]), r["mist"]["n"])
            self.assertEqual((R["rows"][0]["id"], R["rows"][0]["name"], R["rows"][0]["key"]), (f"{col}-kings_pawn", "킹스 폰 오프닝", "1.e4 e5"))
        hints = [w["level"] == "hint" for w in S["weaknesses"]]
        self.assertEqual(hints, sorted(hints))            # 근거 약한 항목은 뒤에 모인다
        json.dumps(S, ensure_ascii=False)                 # 직렬화 가능해야 한다

    def test_purge_unrated(self):
        """친선 대국은 받지 않고, 예전에 받아 둔 것은 한 번 정리한다."""
        urls = [r[0] for r in self.con.execute("SELECT url FROM games ORDER BY end_time")]
        arch = {"archives": ["a1"]}
        games = {"games": [dict(url=urls[0], time_class="rapid", rules="chess", rated=False), dict(url=urls[1], time_class="rapid", rules="chess", rated=True),
                           dict(url="x", time_class="blitz", rules="chess", rated=False)]}
        fetch = lambda url, cfg: arch if url.endswith("/archives") else games
        pipeline.export_missing_games(self.con)
        self.assertTrue(os.path.exists(os.path.join(pipeline.DOCS, "games", pipeline.game_id(urls[0]) + ".json")))
        self.assertEqual(pipeline.purge_unrated(self.con, dict(CHESSCOM_USERNAME="me"), fetch), 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM games").fetchone()[0], 23)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM plies WHERE url=?", (urls[0],)).fetchone()[0], 0)
        self.assertFalse(os.path.exists(os.path.join(pipeline.DOCS, "games", pipeline.game_id(urls[0]) + ".json")))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM games WHERE rated=1").fetchone()[0], 23)
        self.assertEqual(pipeline.purge_unrated(self.con, dict(CHESSCOM_USERNAME="me"), lambda *a: (_ for _ in ()).throw(AssertionError("다시 받으면 안 된다"))), 0)

    def test_endgame_kind(self):
        import chess
        K = pipeline.endgame_kind
        self.assertEqual(K(chess.Board("8/5k2/8/8/8/8/5K2/8 w - - 0 1")), "pawn")
        self.assertEqual(K(chess.Board("8/5k2/8/8/8/8/5K2/4R3 w - - 0 1")), "rook")
        self.assertEqual(K(chess.Board("8/5k2/8/8/8/8/5K2/4RB2 w - - 0 1")), "rook_minor")
        self.assertEqual(K(chess.Board("8/5k2/8/8/8/8/5K2/4NB2 w - - 0 1")), "minor")
        self.assertEqual(K(chess.Board("8/5k2/8/8/8/8/5K2/4Q3 w - - 0 1")), "queen")
        self.assertEqual(K(chess.Board("8/5k2/8/8/8/8/5K2/3rQ3 w - - 0 1")), "queen_more")
        S = pipeline.compute_stats(pipeline.load_games(self.con), self.con)
        self.assertEqual(S["endgames"], [])                                             # 가짜 게임은 2수짜리라 엔드게임이 없다

    def test_finish(self):
        f = pipeline.compute_stats(pipeline.load_games(self.con), self.con)["finish"]
        self.assertEqual(set(f), {"W", "L", "D"})
        self.assertEqual(sum(x["n"] for k in f for x in f[k]), 24)
        self.assertEqual([x["how"] for x in f["W"]], ["resigned"])                   # 가짜 게임: 이긴 판은 상대가 기권
        self.assertEqual([x["how"] for x in f["L"]], ["resigned"])

    def test_color_wdl(self):
        o = pipeline.compute_stats(pipeline.load_games(self.con), self.con)["overview"]
        for c in "wb":
            w = o[f"wdl_{c}"]
            self.assertEqual(w["win"] + w["draw"] + w["loss"], o[f"games_{c}"])
            self.assertAlmostEqual((w["win"] + 0.5 * w["draw"]) / o[f"games_{c}"] * 100, o[f"score_{c}"], places=1)

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
        self.con.execute("DELETE FROM lines")
        every = [dict(san=chess.Board().san(m), uci=m.uci()) for m in chess.Board().legal_moves if m.uci() != "d2d4"]
        self.add_lines(alts=every)
        self.assertEqual(pipeline.export_puzzles(self.con), 0)        # 둘 수 있는 수가 모두 정답인 국면도 뺀다

    def test_moves_cache_and_export(self):
        """모든 수 평가: 할 일 목록은 퍼즐 국면이 먼저이고, 가짜 엔진으로 채우면 퍼즐·연습 라인에 moves 가 붙는다."""
        import chess

        class Eng:                                     # 엔진 대역: 합법 수마다 다른 점수
            def analyse(self, b, limit, multipv=1):
                return [dict(pv=[m], score=chess.engine.PovScore(chess.engine.Cp(50 - 5 * i), b.turn)) for i, m in enumerate(list(b.legal_moves)[:multipv])]
        self.add_lines()
        todo = pipeline.moves_todo(self.con)
        self.assertEqual(todo[0], START)                                         # 퍼즐(백의 첫 수 실수) 국면이 먼저
        self.assertEqual(len(todo), len(set(todo)))
        n, left = pipeline.enrich_moves(self.con, {}, limit=1, eng=Eng())
        self.assertEqual((n, left), (1, len(todo) - 1))
        m = pipeline.cached_moves(self.con, START)
        self.assertEqual(len(m), 20)
        self.assertEqual(m[next(iter(chess.Board().legal_moves)).uci()], 50); self.assertEqual(min(m.values()), 50 - 5 * 19)
        self.assertEqual(pipeline.moves_todo(self.con), todo[1:])                 # 계산한 국면은 할 일에서 빠진다
        pipeline.export_puzzles(self.con)
        pz = json.load(open(os.path.join(pipeline.DOCS, "puzzles.json")))
        self.assertEqual(pz[0]["fen"], START); self.assertEqual(pz[0]["moves"]["e2e4"], m["e2e4"])
        self.assertTrue(all("moves" not in w for w in pz if w["fen"] != START))
        self.assertEqual(max(pipeline.eval_moves(Eng(), "7k/8/8/8/8/8/8/K7 w - - 0 1").values()), 50)
        self.assertEqual(pipeline.eval_moves(Eng(), "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"), {})   # 둘 수 없는 국면(외통)은 빈 결과

    def add_lines_not_ok(self):
        self.con.execute("DELETE FROM lines"); self.add_lines(puzzle_ok=False)

    def test_game_export_and_coach_file(self):
        self.assertEqual(pipeline.export_missing_games(self.con), 24)
        g = json.load(open(os.path.join(pipeline.DOCS, "games", "1000.json")))
        self.assertEqual([p.get("cat") for p in g["plies"]], ["allowed_deep", None])         # 내 수(백)의 400 손해만 유형이 붙는다
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
        self.assertEqual(pipeline.build_book(self.con, pipeline.load_games(self.con)), ({}, 0, 2))   # 엔진 없이: 백·흑 한 묶음씩 덜 만들어진 것으로 센다
        from collections import defaultdict
        idx = pipeline._position_index(pipeline.load_games(self.con))                    # 가짜 게임: 1.e4 e5
        short, _, done = pipeline.book_line(self.con, None, [0], "b", idx, idx)
        self.assertFalse(done); self.assertEqual([p["san"] for p in short], ["e4"])        # 엔진 없이는 캐시가 끝나는 데서 멈춘다
        plies, branches, done = pipeline.book_line(self.con, Eng(), [1000], "b", idx, idx)
        self.assertTrue(done); self.assertEqual(branches, [])
        self.assertGreaterEqual(sum(p["mine"] for p in plies), 6)
        self.assertEqual(plies[0]["san"], "e4"); self.assertEqual(plies[0]["n"], 12)       # 상대의 첫 수는 게임에서 가장 잦은 수
        b = chess.Board()
        for p in plies:                                                                   # 라인의 수는 모두 둘 수 있는 수이고 fen 이 이어진다
            b.push_uci(p["uci"]); self.assertEqual(b.fen(), p["fen"])
        again, _, done = pipeline.book_line(self.con, None, [0], "b", idx, idx)
        self.assertTrue(done); self.assertEqual(again, plies)                              # 다시 만들 때는 캐시만으로
        book, n, pending = pipeline.build_book(self.con, pipeline.load_games(self.con), Eng(), 1000)
        self.assertEqual((sorted(book), pending), (["b-kings_pawn", "w-kings_pawn"], 0))
        self.assertTrue(all(ln["plies"] for o in book.values() for ln in o["lines"]))
        fens = pipeline.book_my_fens(self.con, pipeline.load_games(self.con))
        self.assertIn(START, fens)                                                         # 백 라인의 첫 수 국면
        self.assertTrue(all("moves" not in p for o in book.values() for ln in o["lines"] for p in ln["plies"]))
        self.con.execute("INSERT INTO moves VALUES(?,?,?)", (START, pipeline.MOVES_DEPTH, json.dumps({"e2e4": 30, "d2d4": 25})))
        book = pipeline.build_book(self.con, pipeline.load_games(self.con))[0]
        self.assertEqual(book["w-kings_pawn"]["lines"][0]["plies"][0]["moves"]["d2d4"], 25)  # 모든 수 평가가 있으면 내 수 자리에 붙는다

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

    def test_lessons_build(self):
        """교본 원고의 수순이 전부 둘 수 있고, 유형·오프닝 키가 실제 키이며, 올라간 lessons.json 이 원고와 같다."""
        import re
        import chess
        ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(ROOT, "lessons"))
        import build
        data = build.build()
        ids = [c["id"] for c in data["chapters"]]
        self.assertEqual(len(ids), len(set(ids)))
        parts = {p["id"] for p in data["parts"]}
        for c in data["chapters"]:
            self.assertIn(c["part"], parts)
            self.assertTrue(set(c["cats"]) <= set(pipeline.CAT_KEYS), c["id"])
            self.assertTrue(all(re.match(r"^[wb]-[a-z_]+$", r) for r in c["rep"]), c["id"])
            for b in c["blocks"]:
                if b["t"] == "try":
                    bd = chess.Board(b["fen"]); bd.push_uci(b["uci"])
                    self.assertEqual(bd.fen(), b["after"])
                    self.assertEqual(b["mate"], bd.is_checkmate())
                    self.assertIn("cp", b, "lessons/build.py --eval 로 문제 국면을 평가하세요")
                    self.assertEqual(b["cp"], max(b["moves"].values()))
                    self.assertIn(b["uci"][:4], b["moves"])
                    self.assertGreaterEqual(b["moves"][b["uci"][:4]], b["cp"] - 200, b["san"])      # 정답이 최선과 크게 다르지 않다
                if b["t"] == "line":
                    for ln in b["lines"]:
                        bd = chess.Board(ln["fen"])
                        for p in ln["plies"]:
                            bd.push_uci(p["uci"])
                            self.assertEqual(bd.fen(), p["fen"])
        with open(os.path.join(ROOT, "docs", "lessons.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), json.loads(json.dumps(data)), "lessons/build.py 를 다시 실행하세요")

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
