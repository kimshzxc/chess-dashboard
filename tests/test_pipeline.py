"""스모크 테스트: 통계 계산과 추이 분석이 작은 합성 DB 에서 끝까지 도는지, 통계 함수가 알려진 값을 내는지.
실행: python -m unittest discover -s tests -v"""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pipeline  # noqa: E402

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"


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


class ComputeStats(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        pipeline.DATA = self.tmp.name
        pipeline.DOCS = os.path.join(self.tmp.name, "docs")
        pipeline.DB_PATH = os.path.join(self.tmp.name, "chess.db")
        os.makedirs(pipeline.DOCS)
        self.con = pipeline.db()
        base = 1_790_000_000
        for i in range(24):
            color = "w" if i % 2 == 0 else "b"
            outcome = "L" if i % 3 == 0 else "W"
            url = f"https://www.chess.com/game/live/{1000 + i}"
            # 6판씩 같은 세션(10분 간격), 세션 사이는 하루
            end = base + (i // 6) * 86400 + (i % 6) * 600
            self.con.execute("INSERT INTO games(url,end_time,date,my_color,white,black,welo,belo,opp,opp_elo,my_elo,result,outcome,my_result,"
                             "opp_result,termination,eco,eco_name,time_control,pgn,notified) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
                             (url, end, "2026-0%d-%02d" % (1 + i // 12, 1 + i % 12), color, "me" if color == "w" else "opp",
                              "opp" if color == "w" else "me", 900, 900, "opp", 900, 900 + i, "1-0", outcome,
                              "win" if outcome == "W" else "resigned", "resigned" if outcome == "W" else "win", "x", "C20", "Kings Pawn", "600", ""))
            pipeline.store_analysis(self.con, url, fake_plies(color, 400 if i % 4 == 0 else 20))

    def tearDown(self):
        self.con.close(); self.tmp.cleanup()

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
            self.assertIn(w["trend"]["status"], ("insufficient", "better", "maybe_better", "flat", "maybe_worse", "worse"))
        json.dumps(S, ensure_ascii=False)  # 직렬화 가능해야 한다

    def test_metric_series_all_keys(self):
        games = pipeline.load_games(self.con)
        for key in pipeline.METRICS:
            arg = ["w", "e4 e5"] if key == "opening" else None
            series = pipeline.metric_series(games, key, arg)
            self.assertIsInstance(series, list)

    def test_puzzles_and_reanalysis_queue(self):
        n = pipeline.export_puzzles(self.con)
        self.assertGreater(n, 0)
        pz = json.load(open(os.path.join(pipeline.DOCS, "puzzles.json")))
        self.assertTrue(all(k in pz[0] for k in ("id", "fen", "uci", "best_uci", "wp_loss", "after_fen")))
        # 깊이가 바뀐 게임은 재분석 대기열에 잡힌다
        self.con.execute("UPDATE games SET depth=14 WHERE url LIKE '%1000'")
        redo = self.con.execute("SELECT COUNT(*) FROM games WHERE analyzed=1 AND (depth IS NULL OR depth!=?)", (pipeline.DEPTH,)).fetchone()[0]
        self.assertEqual(redo, 1)


if __name__ == "__main__":
    unittest.main()
