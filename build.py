# -*- coding: utf-8 -*-
"""
一键打包脚本
------------------------------------------------
用法：
    pip install pyinstaller
    python build.py

作用：
    1. 自动定位本机 platform-tools 里的 adb.exe 及其依赖 DLL
    2. 复制到 adb_bundle/
    3. 调 PyInstaller 打成单文件 exe（内置 adb）

产物：dist/MiUninstaller.exe
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# Windows CI 的控制台默认是 cp1252，直接打印中文会 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src" / "mi_uninstaller.py"
ICON = ROOT / "assets" / "icon.ico"
VERINFO = ROOT / "version_info.txt"
ADB_DIR = ROOT / "adb_bundle"
DIST = ROOT / "dist"
WORK = ROOT / "build"

ADB_FILES = ["adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll"]


def find_platform_tools():
    """按优先级查找 platform-tools 目录"""
    cands = []

    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        base = os.environ.get(env)
        if base:
            cands.append(Path(base) / "platform-tools")

    local = os.environ.get("LOCALAPPDATA")
    if local:
        cands.append(Path(local) / "Android" / "Sdk" / "platform-tools")

    home = Path.home()
    cands.append(home / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools")
    cands.append(home / "Library" / "Android" / "sdk" / "platform-tools")

    # 已经在 PATH 里
    which = shutil.which("adb")
    if which:
        cands.append(Path(which).parent)

    for c in cands:
        if (c / "adb.exe").is_file() or (c / "adb").is_file():
            return c
    return None


def prepare_adb():
    if all((ADB_DIR / f).is_file() for f in ADB_FILES):
        print("[1/3] adb_bundle 已就绪，跳过")
        return True

    pt = find_platform_tools()
    if not pt:
        print("[!] 没找到 platform-tools。请任选其一：")
        print("    - 设置环境变量 ANDROID_HOME 指向 Android SDK")
        print("    - 手动把 adb.exe / AdbWinApi.dll / AdbWinUsbApi.dll 放进 adb_bundle/")
        return False

    print(f"[1/3] 从 {pt} 复制 adb 组件")
    ADB_DIR.mkdir(exist_ok=True)
    for name in ADB_FILES:
        src = pt / name
        if src.is_file():
            shutil.copy2(src, ADB_DIR / name)
            print(f"      + {name}")
        else:
            print(f"      ! 缺少 {name}")
    return True


def build():
    print("[2/3] 检查 PyInstaller")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[!] 未安装 PyInstaller，请先执行：pip install pyinstaller")
        return False

    print("[3/3] 开始打包")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile", "--windowed",
        "--name", "MiUninstaller",
        "--icon", str(ICON),
        "--add-binary", f"{ADB_DIR / 'adb.exe'};adb",
        "--add-binary", f"{ADB_DIR / 'AdbWinApi.dll'};adb",
        "--add-binary", f"{ADB_DIR / 'AdbWinUsbApi.dll'};adb",
        "--add-data", f"{ICON};.",
        "--distpath", str(DIST),
        "--workpath", str(WORK),
        "--specpath", str(WORK),
    ]
    # 把作者信息写进 exe 属性（右键 → 详细信息）
    if VERINFO.is_file():
        cmd += ["--version-file", str(VERINFO)]
    cmd.append(str(SRC))

    ret = subprocess.call(cmd)
    if ret != 0:
        print("[!] 打包失败")
        return False

    exe = DIST / "MiUninstaller.exe"
    if exe.is_file():
        size = exe.stat().st_size / 1024 / 1024
        print(f"\n完成：{exe}  ({size:.1f} MB)")
        return True
    print("[!] 没找到产物")
    return False


def main():
    if not prepare_adb():
        return 1
    return 0 if build() else 1


if __name__ == "__main__":
    sys.exit(main())
