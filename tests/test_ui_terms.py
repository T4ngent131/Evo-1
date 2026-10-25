"""不依赖截图或 OCR 模型的游戏界面文字别名检查。"""

import json
import re
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import ui_terms


def parsers():
    """单独运行时用空 OCR 模块载入纯文字函数，不影响完整测试入口。"""
    standalone = "ocr" not in sys.modules
    if standalone:
        ocr = types.ModuleType("ocr")
        ocr.SMALL_CROP_PARAMS = {}
        ocr.create_engine = ocr.load_image = ocr.read_lines = ocr.load_config = lambda *args, **kwargs: None
        sys.modules["ocr"] = ocr
    try:
        import match_start
        import xp_page
        return match_start, xp_page
    finally:
        if standalone:
            del sys.modules["ocr"]


def main():
    match_start, xp_page = parsers()
    checks = {
        "简体模式保持不变": ui_terms.alias_group("modes", "排位赛") == "ranked",
        "繁体模式": ui_terms.alias_group("modes", "排位賽") == "ranked",
        "英文模式": ui_terms.alias_group("modes", "RANKED LEAGUES") == "ranked",
        "英文地图": ui_terms.alias_group("maps", "World's Edge") == "世界尽头",
        "繁体地图": ui_terms.alias_group("maps", "奧林匹斯") == "奥林匹斯",
        "英文段位": ui_terms.tier_prefix("Diamond II") == ("钻石", "ii"),
        "繁体段位": ui_terms.tier_prefix("鑽石 Ⅱ") == ("钻石", "ii"),
        "未知段位不猜": ui_terms.tier_prefix("Unknown II") is None,
    }
    points = re.compile(r"([+-]?\d+)\s*" + ui_terms.POINT_SUFFIX, re.I)
    checks["三种排位点数写法"] = all(points.match(text).group(1) == "-42" for text in
                                     ("-42 排位点数", "-42 排位點數", "-42 Ranked Points"))
    compact_points = re.compile(r"(\d+)/\d+" + ui_terms.POINT_SUFFIX_COMPACT, re.I)
    checks["大厅进度可带英文空格"] = bool(compact_points.search(ui_terms.key("868 / 1000 Ranked Points")))
    checks["多语言画面关键词成组匹配"] = (
        ui_terms.has_keywords("KILLS ASSISTS", [["击杀", "助攻"], ["KILLS", "ASSISTS"]])
        and not ui_terms.has_keywords("KILLS only", [["击杀", "助攻"], ["KILLS", "ASSISTS"]]))
    cfg = json.loads((Path(__file__).resolve().parents[1] / "config" / "match_start.json").read_text(encoding="utf-8"))
    checks["解析英文地图到原有数据名"] = match_start.closest_map("Storm Point", cfg) == "风暴点"
    checks["英文下一段位"] = xp_page.current_rank("Next Rank: Diamond I") == ("钻石", "II")
    checks["繁体下一段位"] = xp_page.current_rank("下一段位: 鑽石Ⅱ") == ("钻石", "III")
    for label, ok in checks.items():
        print(f"{'OK' if ok else 'FAIL'} {label}")
    return all(checks.values())


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
