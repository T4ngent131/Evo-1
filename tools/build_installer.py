"""把 dist/Evo 文件夹制成单文件 Windows 安装器。先运行 tools/build.py。"""

import os
import shutil
import subprocess
from pathlib import Path

import code_path  # noqa: F401
from storage import APP_VERSION

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "installer.iss"
DIST = ROOT / "dist" / "Evo"


def compiler():
    override = os.environ.get("INNO_ISCC")
    if override:
        return Path(override)
    found = shutil.which("ISCC.exe")
    if found:
        return Path(found)
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 7" / "ISCC.exe"
    if local.is_file():
        return local
    raise SystemExit("找不到 Inno Setup 7 的 ISCC.exe；安装后可用 INNO_ISCC 指定路径")


def main():
    if not (DIST / "Evo.exe").is_file():
        raise SystemExit("没有 dist/Evo/Evo.exe；请先运行 tools/build.py")
    for folder in ("av.libs", "soundcard"):
        if not (DIST / "_internal" / folder).is_dir():
            raise SystemExit(f"安装包缺少 {folder}；请安装 requirements-highlights.txt 并重新打包")
    tool = compiler()
    if not tool.is_file():
        raise SystemExit(f"找不到 Inno Setup 编译器：{tool}")
    subprocess.run([str(tool), f"/DAppVersion={APP_VERSION}", str(SCRIPT)], cwd=ROOT, check=True)
    package = ROOT / "dist" / f"Evo-{APP_VERSION}-Setup-win64.exe"
    print(f"安装器：{package}（{package.stat().st_size / 1024 ** 2:.1f} MB）")


if __name__ == "__main__":
    main()
