"""无需图像依赖的宽屏坐标换算检查。"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import layout
import game_aspect


def main():
    base = (1920, 1080)
    wide = layout.Mapping((1080, 2520), base)
    checks = {
        "16:9 unchanged": layout.Mapping((1080, 1920), base, "bottom").box([100, 100, 20, 10])
                          == (100, 100, 120, 110),
        "left pinned": wide.box([100, 100, 20, 10]) == (100, 100, 120, 110),
        "center pinned": wide.box([900, 500, 120, 20]) == (1200, 500, 1320, 520),
        "right pinned": wide.box([1700, 100, 100, 20]) == (2300, 100, 2400, 120),
        "stretched wide": layout.Mapping((1440, 2560), base, aspect=21 / 9).box([900, 500, 120, 20])
                          == (1219, 667, 1341, 693),
        "16:10 unchanged": layout.Mapping((1200, 1920), base, "bottom").box([100, 1000, 20, 10])
                           == (100, 1120, 120, 1130),
        "3440x1440 named 21:9": game_aspect.name(3440 / 1440) == "21:9",
    }
    with tempfile.TemporaryDirectory() as folder:
        config = Path(folder) / "videoconfig.txt"
        config.write_text('"setting.fullscreen" "1"\n"setting.defaultres" "2520"\n'
                          '"setting.defaultresheight" "1080"\n', encoding="utf-8")
        checks["fullscreen 21:9 detected"] = game_aspect.from_video_config(config)[0] == 21 / 9
    for label, ok in checks.items():
        print(f"{'OK' if ok else 'FAIL'} {label}")
    return all(checks.values())


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
