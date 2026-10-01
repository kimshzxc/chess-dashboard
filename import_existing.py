#!/usr/bin/env python3
"""이미 분석해 둔 analysis.json + rapid_games.json 을 DB로 가져온다 (재분석 방지). 1회용."""
import json, re, sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline as P

src = sys.argv[1] if len(sys.argv) > 1 else "."
analysis = json.load(open(os.path.join(src, "analysis.json")))
raw = {g["url"]: g for g in json.load(open(os.path.join(src, "rapid_games.json")))}
me = P.load_env()["CHESSCOM_USERNAME"].lower()
con = P.db()
known = {r[0] for r in con.execute("SELECT url FROM games")}
n = 0
for a in analysis:
    g = raw.get(a["link"])
    if not g or g["url"] in known:
        continue
    side = "white" if g["white"]["username"].lower() == me else "black"
    opp = "black" if side == "white" else "white"
    r = g[side]["result"]
    outcome = "W" if r == "win" else ("D" if r in P.OUTCOME_DRAW else "L")
    hdr = dict(re.findall(r'\[(\w+) "([^"]*)"\]', g["pgn"]))
    row = dict(url=g["url"], end_time=g["end_time"],
               date=datetime.fromtimestamp(g["end_time"], P.KST).strftime("%Y-%m-%d"),
               my_color="w" if side == "white" else "b", white=g["white"]["username"], black=g["black"]["username"],
               welo=g["white"]["rating"], belo=g["black"]["rating"], opp=g[opp]["username"], opp_elo=g[opp]["rating"],
               my_elo=g[side]["rating"], result=hdr.get("Result"), outcome=outcome, my_result=r, opp_result=g[opp]["result"],
               termination=hdr.get("Termination"), eco=hdr.get("ECO"),
               eco_name=hdr.get("ECOUrl", "").rsplit("/", 1)[-1].replace("-", " "),
               time_control=g.get("time_control"), pgn=g["pgn"])
    con.execute("INSERT INTO games(url,end_time,date,my_color,white,black,welo,belo,opp,opp_elo,my_elo,"
                "result,outcome,my_result,opp_result,termination,eco,eco_name,time_control,pgn,notified) "
                "VALUES(:url,:end_time,:date,:my_color,:white,:black,:welo,:belo,:opp,:opp_elo,:my_elo,"
                ":result,:outcome,:my_result,:opp_result,:termination,:eco,:eco_name,:time_control,:pgn,1)", row)
    plies = []
    for p in a["plies"]:
        plies.append(dict(ply=p["ply"], move=p["move"], mover=p["mover"], mine=int(p["mine"]), san=p["san"], best=p["best"],
                          is_best=int(p["is_best"]), cp_before=p["cp_before"], cp_after=p["cp_after"], loss=p["loss"],
                          wp_loss=p["wp_loss"], clock=p["clock"], spent=p["spent"], capture=int(p["capture"]),
                          chk=int(p["check"]), piece=p["piece"], phase=p["phase"], fen=p["fen"]))
    P.store_analysis(con, g["url"], plies)
    n += 1
print(f"imported {n} games; total {con.execute('SELECT count(*) FROM games').fetchone()[0]}")
