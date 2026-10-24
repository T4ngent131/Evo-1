"""可信读数与账号隔离的回归测试。"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from types import SimpleNamespace

# fake_game must be imported before project code: it creates an isolated data directory.
import fake_game
import calibration
import storage
import numpy as np
import live_collect
from summary_page import read_summary, summary_to_match
from post_match import SAME_MATCH_SECONDS
from post_match import SOURCE_HUD, SOURCE_SUMMARY, PostMatch, settle


def test_readings_keep_raw_status_and_settle_ignores_rejected_summary():
    """若删掉 status 过滤，低分总结页会覆盖可信 HUD 读数。"""
    conn = storage.connect(":memory:")
    match_id = storage.insert_match(conn, {"ended_at": "2026-10-24 20:00:00"})
    storage.save_readings(conn, match_id, SOURCE_SUMMARY, {"kills": 99, "damage": 99999},
                          "2026-10-24 20:00:00", {"kills": .1, "damage": .1},
                          statuses={"kills": "low_score", "damage": "out_of_range"},
                          raw_texts={"kills": "99", "damage": "99999"})
    storage.save_readings(conn, match_id, SOURCE_HUD, {"kills": 2, "damage": 600}, "2026-10-24 20:00:01")
    settle(conn, match_id)
    settle(conn, match_id)  # 重复归并也不得使被拒绝值回流
    row = storage.get_match(conn, match_id)
    readings = {r["field"]: r for r in storage.readings_of(conn, match_id) if r["source"] == SOURCE_SUMMARY}
    assert (row["kills"], row["damage"], row["needs_review"]) == (2, 600, 1)
    assert (readings["kills"]["status"], readings["kills"]["raw_text"]) == ("low_score", "99")
    conn.close()


def test_migration_preserves_historical_null_reading_status():
    """升级只加列；旧 readings 行的 status/raw_text 保持 NULL。"""
    conn = storage.connect(":memory:")
    conn.execute("PRAGMA user_version = 7")
    conn.execute("DROP TABLE readings")
    conn.execute("CREATE TABLE readings (match_id INTEGER NOT NULL, field TEXT NOT NULL, source TEXT NOT NULL, value, score REAL, read_at TEXT, PRIMARY KEY (match_id, field, source))")
    conn.execute("INSERT INTO readings VALUES (1, 'kills', '总结页', 3, .9, '2026-10-24 20:00:00')")
    conn.commit()
    storage._upgrade(conn)
    row = conn.execute("SELECT status, raw_text FROM readings").fetchone()
    assert tuple(row) == (None, None)
    conn.close()


def test_calibration_does_not_cross_unknown_or_different_players():
    """若放宽玩家过滤，未知/不同账号局会被错误补 RP 或段位。"""
    conn = storage.connect(":memory:")
    t = datetime(2026, 10, 24, 20)
    unknown = storage.insert_match(conn, {"ended_at": (t + timedelta(minutes=1)).strftime("%F %T"), "mode": "ranked"})
    other = storage.insert_match(conn, {"ended_at": (t + timedelta(minutes=2)).strftime("%F %T"), "mode": "ranked", "player_name": "Other"})
    for minute, name, progress in ((0, "Me", 900), (3, "Me", 850)):
        reading = {"read_at": (t + timedelta(minutes=minute)).strftime("%F %T"), "player_name": name,
                   "rank_tier": "钻石", "rank_division": "II", "rank_progress": progress,
                   "score": 14900 + progress}
        storage.save_lobby(conn, reading)
        calibration.calibrate(conn, reading)
    assert storage.get_match(conn, unknown)["rp_delta"] is None
    assert storage.get_match(conn, other)["rp_delta"] is None
    assert storage.get_match(conn, unknown)["rank_tier"] is None
    assert storage.get_match(conn, other)["rank_tier"] is None
    conn.close()


def _summary_results(placement=3):
    return {
        "placement": {"value": placement, "status": "ok", "score": .9, "raw": str(placement)},
        "kda": {"value": (2, 1, 0), "status": "ok", "score": .9, "raw": "2/1/0"},
        "damage": {"value": 600, "status": "ok", "score": .9, "raw": "600"},
        "squad_kills": {"value": 3, "status": "ok", "score": .9, "raw": "3"},
        "survival_time": {"value": "10:00", "status": "ok", "score": .9, "raw": "10:00"},
        "revives": {"value": 0, "status": "ok", "score": .9, "raw": "0"},
        "respawns": {"value": 0, "status": "ok", "score": .9, "raw": "0"},
    }


def test_summary_dedup_uses_round_token_and_time_window():
    """若去掉 token 或时间窗，同局回切/同数据新局会分别重复或被永久吞掉。"""
    conn = storage.connect(":memory:")
    post = PostMatch(conn, log=lambda _: None)
    run_dir = fake_game._TEMP / "dedup"
    run_dir.mkdir(exist_ok=True)
    watcher = live_collect.SummaryWatcher(None, {}, conn, post, run_dir, lambda _: None, timeout=30)
    results, frame = _summary_results(), np.zeros((10, 10, 3), np.uint8)
    with mock.patch("live_collect.read_teammates", return_value=[]):
        watcher._record(results, [], frame, datetime(2026, 10, 24, 20))
        watcher._record(results, [], frame, datetime(2026, 10, 24, 20, 0, 1))
        assert len(storage.recent_matches(conn)) == 1
        post.finish()
        watcher._record(results, [], frame, datetime(2026, 10, 24, 20, 0, 2))
        assert len(storage.recent_matches(conn)) == 2
        watcher._record(results, [], frame, datetime(2026, 10, 24, 20) + timedelta(seconds=SAME_MATCH_SECONDS + 3))
    assert len(storage.recent_matches(conn)) == 3
    conn.close()


def test_champion_summary_without_placement_is_saved():
    """若把缺少名次当作整局无效，冠军总结页会被丢掉。"""
    conn = storage.connect(":memory:")
    post = PostMatch(conn, log=lambda _: None)
    run_dir = fake_game._TEMP / "champion"
    run_dir.mkdir(exist_ok=True)
    watcher = live_collect.SummaryWatcher(None, {}, conn, post, run_dir, lambda _: None, timeout=30)
    results = _summary_results(None)
    results["placement"] = {"value": None, "status": "not_found", "score": None, "raw": ""}
    frame, when = np.zeros((10, 10, 3), np.uint8), datetime(2026, 10, 24, 20)
    with mock.patch("live_collect.read_teammates", return_value=[]):
        watcher._record(results, ["名次：没读到（OCR 原文：无）"], frame, when)
    post.on_champion(when, SOURCE_SUMMARY)
    row = storage.recent_matches(conn)[0]
    assert (row["placement"], row["kills"], row["needs_review"]) == (1, 2, 0)
    conn.close()


def test_calibration_fills_missing_rp_for_same_known_player():
    """若错误地禁用全部校准，同名已知玩家的唯一缺失 RP 不会补上。"""
    conn = storage.connect(":memory:")
    t = datetime(2026, 10, 24, 20)
    match_id = storage.insert_match(conn, {"ended_at": (t + timedelta(minutes=1)).strftime("%F %T"),
                                           "mode": "ranked", "player_name": "Me"})
    for minute, progress in ((0, 900), (2, 850)):
        reading = {"read_at": (t + timedelta(minutes=minute)).strftime("%F %T"), "player_name": "Me",
                   "rank_tier": "钻石", "rank_division": "II", "rank_progress": progress,
                   "score": 14900 + progress}
        storage.save_lobby(conn, reading)
        calibration.calibrate(conn, reading)
    assert storage.get_match(conn, match_id)["rp_delta"] == -50
    conn.close()


def test_calibration_skips_none_and_whitespace_player_names():
    """若把未知或空白名当作账号，校准会错误补 RP 和段位。"""
    for name in (None, "   "):
        conn = storage.connect(":memory:")
        match_id = storage.insert_match(conn, {"ended_at": "2026-10-24 20:01:00", "mode": "ranked", "player_name": name})
        reading = {"read_at": "2026-10-24 20:02:00", "player_name": name, "rank_tier": "钻石",
                   "rank_division": "II", "rank_progress": 850, "score": 15750}
        calibration.calibrate(conn, reading)
        row = storage.get_match(conn, match_id)
        assert (row["rp_delta"], row["rank_tier"]) == (None, None)
        conn.close()


def test_read_summary_flags_low_score_non_key_and_sanitizes_match():
    """若忽略非关键低分字段，revives 会悄悄写进正式战绩。"""
    fields = {name: {"label": name, "roi": [0, 0, 1, 1], "expect": expect,
                     "range": None if expect == "duration" else [0, 999]}
              for name, expect in (("placement", "integer"), ("kda", "kda"), ("damage", "integer"),
                                   ("squad_kills", "integer"), ("survival_time", "duration"),
                                   ("revives", "integer"), ("respawns", "integer"))}
    cfg = {"base_resolution": [1, 1], "upscale": 1, "replace": {}, "min_score": .8, "fields": fields}
    outputs = iter((("3", .9), ("2/1/0", .9), ("600", .9), ("3", .9), ("10:00", .9), ("5", .1), ("0", .9)))
    def engine(_):
        text, score = next(outputs)
        return SimpleNamespace(txts=[text], scores=[score])
    results, problems = read_summary(engine, np.zeros((1, 1, 3), np.uint8), cfg)
    match = summary_to_match(results, problems, "2026-10-24 20:00:00")
    assert results["revives"]["status"] == "low_score"
    assert any(p.startswith("revives") for p in problems)
    assert (match["revives"], match["needs_review"]) == (None, 1)


def test_settle_keeps_user_edited_fields_but_updates_other_fields():
    """若 settle 回写 edited 字段，面板人工修正会被旧来源覆盖并重新标复核。"""
    conn = storage.connect(":memory:")
    match_id = storage.insert_match(conn, {"ended_at": "2026-10-24 20:00:00"})
    storage.save_readings(conn, match_id, SOURCE_SUMMARY,
                          {"placement": 8, "kills": 3, "assists": 1, "damage": 688, "rp_delta": -20},
                          "2026-10-24 20:00:00",
                          statuses={"kills": "low_score", "damage": "low_score"})
    storage.save_readings(conn, match_id, SOURCE_HUD, {"kills": 4, "assists": 1, "damage": 700},
                          "2026-10-24 20:00:01")
    storage.update_match(conn, match_id, {"placement": 1, "kills": 9, "damage": 1600, "rp_delta": 50,
                                          "edited": "placement,kills,damage,rp_delta", "needs_review": 0,
                                          "review_note": None})
    settle(conn, match_id)
    settle(conn, match_id)
    row = storage.get_match(conn, match_id)
    assert (row["placement"], row["kills"], row["damage"], row["rp_delta"], row["assists"], row["needs_review"]) \
        == (1, 9, 1600, 50, 1, 0)
    storage.save_readings(conn, match_id, SOURCE_SUMMARY, {"revives": 8},
                          "2026-10-24 20:00:02", statuses={"revives": "low_score"})
    settle(conn, match_id)
    row = storage.get_match(conn, match_id)
    assert row["needs_review"] == 1
    assert (row["placement"], row["kills"], row["damage"], row["rp_delta"]) == (1, 9, 1600, 50)
    assert "revives" in row["review_note"]
    conn.close()


def test_summary_watcher_preserves_untrusted_key_candidate_on_leave():
    """若恢复按 value 判完整，低分 KDA 会被 SummaryWatcher 写成正式战绩。"""
    conn = storage.connect(":memory:")
    post = PostMatch(conn, log=lambda _: None)
    run_dir = fake_game._TEMP / "reliability"
    run_dir.mkdir(exist_ok=True)
    watcher = live_collect.SummaryWatcher(None, {}, conn, post, run_dir, lambda _: None, timeout=30)
    results = {
        "placement": {"value": 3, "status": "ok", "score": .9, "raw": "3"},
        "kda": {"value": (2, 1, 0), "status": "low_score", "score": .1, "raw": "2/1/0"},
        "damage": {"value": 600, "status": "ok", "score": .9, "raw": "600"},
        "squad_kills": {"value": 3, "status": "ok", "score": .9, "raw": "3"},
        "survival_time": {"value": None, "status": "not_found", "score": None, "raw": ""},
        "revives": {"value": None, "status": "not_found", "score": None, "raw": ""},
        "respawns": {"value": None, "status": "not_found", "score": None, "raw": ""},
    }
    frame = np.zeros((10, 10, 3), np.uint8)
    with mock.patch("live_collect.read_summary", return_value=(results, ["KDA low score"])), \
            mock.patch("live_collect.read_teammates", return_value=[]):
        watcher.update(True, frame, datetime(2026, 10, 24, 20))
        watcher.update(False, frame, datetime(2026, 10, 24, 20, 0, 1))
    row = storage.recent_matches(conn)[0]
    readings = {r["field"]: r for r in storage.readings_of(conn, row["match_id"])}
    assert (row["placement"], row["kills"], row["damage"], row["needs_review"]) == (3, None, 600, 1)
    assert (readings["kills"]["value"], readings["kills"]["status"], readings["kills"]["raw_text"]) == (2, "low_score", "2/1/0")
    conn.close()


def main():
    tests = [test_readings_keep_raw_status_and_settle_ignores_rejected_summary,
             test_migration_preserves_historical_null_reading_status,
             test_calibration_does_not_cross_unknown_or_different_players,
             test_calibration_fills_missing_rp_for_same_known_player,
             test_calibration_skips_none_and_whitespace_player_names,
             test_read_summary_flags_low_score_non_key_and_sanitizes_match,
             test_settle_keeps_user_edited_fields_but_updates_other_fields,
             test_summary_dedup_uses_round_token_and_time_window,
             test_champion_summary_without_placement_is_saved,
             test_summary_watcher_preserves_untrusted_key_candidate_on_leave]
    for test in tests:
        test()
    return True


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
