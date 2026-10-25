"""游戏界面 OCR 文字的别名。只转换固定 UI 词，不改玩家名和原始读数。"""

import json
import re
import unicodedata

from paths import CONFIG_DIR

TERMS = json.loads((CONFIG_DIR / "ui_terms.json").read_text(encoding="utf-8"))


def key(text):
    """比较固定 UI 词时忽略空白、大小写和全角字符。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def alias_group(group, text):
    """别名精确匹配，返回数据库使用的名称。"""
    value = key(text)
    for canonical, aliases in TERMS[group].items():
        if value in {key(one) for one in (canonical, *aliases)}:
            return canonical
    return None


def has_keywords(text, groups):
    """一组里的词都出现即匹配；多组是不同语言的候选。"""
    found = key(text)
    return any(all(key(word) in found for word in group) for group in groups)


def tier_prefix(text):
    """段位名从文字开头匹配，返回 (规范名, 去掉段位名的剩余文字)。"""
    normalized = key(text)
    candidates = [(key(alias), canonical) for canonical, aliases in TERMS["tiers"].items()
                  for alias in (canonical, *aliases)]
    for prefix, canonical in sorted(candidates, key=lambda x: len(x[0]), reverse=True):
        if normalized.startswith(prefix):
            return canonical, normalized[len(prefix):]
    return None


POINT_SUFFIX = "(?:" + "|".join(re.escape(one) for one in sorted(TERMS["points"], key=len, reverse=True)) + ")"
POINT_SUFFIX_COMPACT = "(?:" + "|".join(re.escape(key(one)) for one in sorted(TERMS["points"], key=len, reverse=True)) + ")"
