# -*- coding: utf-8 -*-
"""
小米预装应用卸载助手
------------------------------------------------
一个不依赖 Android Studio 的独立小工具：
内置 adb，启动即自动检测手机，一键卸载小米机型上的预装/推广类应用。

支持：
  - USB 连接、无线调试（自动发现 + 手动 IP:端口）
  - 应用状态检测（是否已安装、版本、安装位置、系统应用标记）
  - 卸载前自动备份 APK 到桌面
  - 一键卸载（--user 0，可逆）/ 一键恢复（install-existing）
  - 关键系统应用保护，防止误删变砖
"""

import os
import re
import sys
import subprocess
import threading
import datetime
import shutil
import tempfile
import ctypes
import webbrowser

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

APP_NAME = "小米预装应用卸载助手"
APP_VER = "1.2"

# 作者署名 / 项目主页
GH_USER = "chokoketsu"
GH_URL = "https://github.com/chokoketsu/SystemHelper-Remover"

# 演示模式：使用模拟设备数据，便于截图和界面预览，不接触真机
DEMO = "--demo" in sys.argv

# 默认目标：联通设备注册组件（用户本次要处理的）
DEFAULT_PKG = "com.mobiletools.systemhelper"

CREATE_NO_WINDOW = 0x08000000

# ---------------------------------------------------------------- 保护名单
# 这些包一旦卸载会直接影响开机、通话、系统 UI，工具拒绝操作
PROTECTED_PKGS = {
    "android",
    "com.android.systemui",
    "com.android.settings",
    "com.android.phone",
    "com.android.providers.settings",
    "com.android.providers.media",
    "com.android.providers.telephony",
    "com.android.providers.contacts",
    "com.android.shell",
    "com.android.packageinstaller",
    "com.miui.home",
    "com.miui.securitycenter",
    "com.miui.securitycore",
    "com.miui.powerkeeper",
    "com.miui.notification",
    "com.xiaomi.misettings",
    "com.android.server.telecom",
    "com.qualcomm.qti.services.systemhelper",
}

# 常用预设（灰度预装 / 推广类，相对安全可移除）
PRESETS = [
    ("com.mobiletools.systemhelper", "联通设备注册组件 SystemHelper（隐藏无图标）"),
    ("com.miui.systemAdSolution", "系统广告服务（关闭广告推荐）"),
    ("com.miui.analytics", "小米分析统计"),
    ("com.miui.msa.global", "MSA 广告标识服务"),
    ("com.xiaomi.mipicks", "小米应用中心推荐"),
    ("com.miui.hybrid", "快应用框架"),
    ("com.miui.video", "小米视频"),
    ("com.miui.news", "小米新闻资讯"),
    ("com.miui.browser", "小米浏览器"),
    ("com.xiaomi.gamecenter", "小米游戏中心"),
    ("com.xiaomi.gsgservice", "游戏服务框架"),
    ("com.miui.miservice", "服务与反馈"),
    ("com.iflytek.inputmethod.miui", "讯飞输入法（小米定制）"),
    ("com.xiaomi.market", "小米应用商店"),
]


# ---------------------------------------------------------------- 资源定位
def resource_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def find_adb():
    """按优先级查找 adb：内置 > 解包目录 > 程序同级 > 系统 SDK > PATH"""
    cands = []
    rd = resource_dir()
    cands.append(os.path.join(rd, "adb", "adb.exe"))
    cands.append(os.path.join(rd, "adb.exe"))
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        cands.append(os.path.join(exe_dir, "adb", "adb.exe"))
        cands.append(os.path.join(exe_dir, "adb.exe"))
    local = os.environ.get("LOCALAPPDATA", "")
    cands.append(os.path.join(local, "Android", "Sdk", "platform-tools", "adb.exe"))
    cands.append(os.path.join(os.environ.get("ProgramFiles", ""), "platform-tools", "adb.exe"))
    w = shutil.which("adb")
    if w:
        cands.append(w)
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


ADB = find_adb()


def run_adb(args, timeout=45, serial=None):
    """执行 adb 命令，返回 (returncode, 合并输出)"""
    if not ADB:
        return 127, "未找到 adb"
    cmd = [ADB]
    if serial:
        cmd += ["-s", serial]
    cmd += args
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
            cwd=os.path.dirname(ADB) or None,
        )
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out
    except subprocess.TimeoutExpired:
        return 124, "命令超时（%ss）" % timeout
    except Exception as e:
        return 1, "命令执行失败：%s" % e


# ---------------------------------------------------------------- 主界面
class App:
    def __init__(self, root):
        self.root = root
        self.serial = None
        self.busy = False
        self._dev_map = {}
        self.backup_root = os.path.join(os.path.expanduser("~"), "Desktop")

        root.title("%s v%s%s" % (APP_NAME, APP_VER, "" if ADB else "（未找到 adb）"))
        root.geometry("880x660")
        root.minsize(820, 600)

        self._build_style()
        self._build_ui()

        self.log("=" * 62)
        self.log("%s v%s 启动" % (APP_NAME, APP_VER))
        self.log("项目主页：%s" % GH_URL, "cmd")
        if ADB:
            # 演示模式不回显真实路径，避免截图时带出本机用户名
            self.log("adb 路径：%s" % ("内置 adb（运行时释放到临时目录）" if DEMO else ADB))
        else:
            self.log("!! 未找到 adb，请确认程序完整或系统已安装 platform-tools", "err")
        self.log("=" * 62)

        self.root.after(200, self.refresh_devices)

    # ------------------------------------------------------------ 样式
    def _build_style(self):
        st = ttk.Style()
        try:
            st.theme_use("vista")
        except Exception:
            pass
        st.configure("TLabel", font=("Microsoft YaHei UI", 9))
        st.configure("TButton", font=("Microsoft YaHei UI", 9), padding=(8, 4))
        st.configure("Big.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(12, 8))
        st.configure("Title.TLabel", font=("Microsoft YaHei UI", 13, "bold"))
        st.configure("Sub.TLabel", font=("Microsoft YaHei UI", 9), foreground="#666666")
        st.configure("Ok.TLabel", font=("Microsoft YaHei UI", 9, "bold"), foreground="#1a7f37")
        st.configure("Bad.TLabel", font=("Microsoft YaHei UI", 9, "bold"), foreground="#c62828")
        st.configure("Treeview", font=("Microsoft YaHei UI", 9), rowheight=24)
        st.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))
        # 署名链接样式
        st.configure("Link.TLabel", font=("Microsoft YaHei UI", 9), foreground="#0b5cad")

    # ------------------------------------------------------------ 界面
    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        # 标题
        head = ttk.Frame(self.root)
        head.pack(fill="x", padx=14, pady=(12, 2))
        ttk.Label(head, text=APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(
            head, text="内置 adb · 无需 Android Studio · 卸载可逆",
            style="Sub.TLabel"
        ).pack(side="left", padx=(10, 0))
        # 右上角署名
        self.lbl_gh_top = ttk.Label(
            head, text="github.com/%s" % GH_USER, style="Link.TLabel", cursor="hand2"
        )
        self.lbl_gh_top.pack(side="right")
        self.lbl_gh_top.bind("<Button-1>", lambda e: self.open_github())
        self.lbl_gh_top.bind(
            "<Enter>", lambda e: self.lbl_gh_top.configure(foreground="#1a7f37")
        )
        self.lbl_gh_top.bind(
            "<Leave>", lambda e: self.lbl_gh_top.configure(foreground="#0b5cad")
        )

        # ---------------- 设备区
        dev = ttk.LabelFrame(self.root, text=" 1. 设备 ")
        dev.pack(fill="x", padx=14, pady=(10, 6))

        row1 = ttk.Frame(dev)
        row1.pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(row1, text="已连接设备：").pack(side="left")
        self.cmb_dev = ttk.Combobox(row1, state="readonly", width=58)
        self.cmb_dev.pack(side="left", padx=(0, 8))
        self.cmb_dev.bind("<<ComboboxSelected>>", lambda e: self._on_dev_change())
        self.btn_refresh = ttk.Button(row1, text="刷新设备", command=self.refresh_devices)
        self.btn_refresh.pack(side="left")

        row2 = ttk.Frame(dev)
        row2.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(row2, text="无线调试地址：").pack(side="left")
        self.ent_ip = ttk.Entry(row2, width=20)
        self.ent_ip.pack(side="left")
        self.ent_ip.insert(0, "192.168.1.100:5555")
        ttk.Button(row2, text="连接", command=self.wifi_connect).pack(side="left", padx=6)
        ttk.Button(row2, text="自动发现", command=self.wifi_discover).pack(side="left")
        self.lbl_dev = ttk.Label(row2, text="状态：未检测", style="Sub.TLabel")
        self.lbl_dev.pack(side="left", padx=(14, 0))

        # ---------------- 应用区
        app = ttk.LabelFrame(self.root, text=" 2. 目标应用 ")
        app.pack(fill="x", padx=14, pady=6)

        row3 = ttk.Frame(app)
        row3.pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(row3, text="包名：").pack(side="left")
        self.cmb_pkg = ttk.Combobox(row3, width=46, values=[p[0] for p in PRESETS])
        self.cmb_pkg.pack(side="left")
        self.cmb_pkg.set(DEFAULT_PKG)
        ttk.Button(row3, text="检测状态", command=self.check_app).pack(side="left", padx=6)
        self.lbl_pkg = ttk.Label(row3, text="状态：未检测", style="Sub.TLabel")
        self.lbl_pkg.pack(side="left", padx=(8, 0))

        row4 = ttk.Frame(app)
        row4.pack(fill="x", padx=10, pady=(2, 4))
        ttk.Label(
            row4,
            text="预设说明：%s" % dict(PRESETS).get(DEFAULT_PKG, "自定义包名"),
            style="Sub.TLabel",
        ).pack(side="left")

        row5 = ttk.Frame(app)
        row5.pack(fill="x", padx=10, pady=(4, 10))
        self.chk_backup = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            row5, text="卸载前自动备份 APK 到桌面", variable=self.chk_backup
        ).pack(side="left")
        self.btn_restore = ttk.Button(row5, text="恢复", command=self.restore_app)
        self.btn_restore.pack(side="right")
        self.btn_uninstall = ttk.Button(
            row5, text="一键卸载", style="Big.TButton", command=self.uninstall_app
        )
        self.btn_uninstall.pack(side="right", padx=8)

        # ---------------- 日志区
        logf = ttk.LabelFrame(self.root, text=" 3. 运行日志 ")
        logf.pack(fill="both", expand=True, padx=14, pady=(6, 4))
        self.txt = scrolledtext.ScrolledText(
            logf, wrap="word", font=("Consolas", 9), height=14,
            bg="#fbfbfb", relief="flat", borderwidth=1
        )
        self.txt.pack(fill="both", expand=True, padx=8, pady=8)
        self.txt.tag_config("info", foreground="#333333")
        self.txt.tag_config("ok", foreground="#1a7f37")
        self.txt.tag_config("err", foreground="#c62828")
        self.txt.tag_config("warn", foreground="#b26a00")
        self.txt.tag_config("cmd", foreground="#0b5cad")
        self.txt.configure(state="disabled")

        # 底部：左侧提示，右侧署名
        foot = ttk.Frame(self.root)
        foot.pack(fill="x", padx=16, pady=(0, 10))
        ttk.Label(
            foot,
            text="提示：卸载采用 pm uninstall --user 0，只移除当前用户的安装，系统分区本体不动，可随时恢复。"
                 "系统大版本升级后可能被重新预置。",
            style="Sub.TLabel",
        ).pack(side="left")

        self.lbl_gh_bottom = ttk.Label(
            foot, text="♥ %s" % GH_USER, style="Link.TLabel", cursor="hand2"
        )
        self.lbl_gh_bottom.pack(side="right")
        self.lbl_gh_bottom.bind("<Button-1>", lambda e: self.open_github())
        self.lbl_gh_bottom.bind(
            "<Enter>", lambda e: self.lbl_gh_bottom.configure(foreground="#1a7f37")
        )
        self.lbl_gh_bottom.bind(
            "<Leave>", lambda e: self.lbl_gh_bottom.configure(foreground="#0b5cad")
        )

    def open_github(self):
        try:
            webbrowser.open(GH_URL)
        except Exception:
            pass
        self.log("项目主页：%s" % GH_URL, "cmd")

    # ------------------------------------------------------------ 工具
    def log(self, msg, tag="info"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.txt.configure(state="normal")
        self.txt.insert("end", "[%s] %s\n" % (ts, msg), tag)
        self.txt.see("end")
        self.txt.configure(state="disabled")
        self.root.update_idletasks()

    def bg(self, fn, *a):
        if self.busy:
            self.log("上一个操作还在进行，请稍候…", "warn")
            return
        self.busy = True
        self._set_buttons("disabled")
        t = threading.Thread(target=self._wrap, args=(fn, a), daemon=True)
        t.start()

    def _wrap(self, fn, a):
        try:
            fn(*a)
        except Exception as e:
            self.log("异常：%s" % e, "err")
        finally:
            self.busy = False
            self.root.after(0, lambda: self._set_buttons("normal"))

    def _set_buttons(self, state):
        for b in (self.btn_refresh, self.btn_uninstall, self.btn_restore):
            try:
                b.configure(state=state)
            except Exception:
                pass

    def _on_dev_change(self):
        sel = self.cmb_dev.get()
        serial = self._dev_map.get(sel, sel)
        if serial:
            self.serial = serial
            self.log("已选择设备：%s" % serial)
            self.check_app(silent=True)

    # ------------------------------------------------------------ 设备
    def refresh_devices(self):
        if DEMO:
            self.log("演示模式：使用模拟设备数据，不会操作真机", "warn")
            self.root.after(300, lambda: self._fill_devices(
                [("DEMO0000000000", "device", "2211133C", "USB")]))
            return
        self.bg(self._refresh_devices)

    def _refresh_devices(self):
        rc, out = run_adb(["start-server"], timeout=30)
        rc, out = run_adb(["devices", "-l"], timeout=30)
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        items = []
        for l in lines[1:]:
            if l.startswith("*") or " daemon " in l:
                continue
            parts = l.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]
            model = ""
            m = re.search(r"model:(\S+)", l)
            if m:
                model = m.group(1)
            kind = "无线" if ("_adb-tls" in serial or ":" in serial) else "USB"
            items.append((serial, state, model, kind))

        self.root.after(0, lambda: self._fill_devices(items))

    def _fill_devices(self, items):
        ready = [i for i in items if i[1] == "device"]
        labels = []
        self._dev_map = {}
        for serial, state, model, kind in items:
            short = serial
            short = serial
            if kind == "无线":
                # mDNS 序列号形如 adb-1a2b3c4d-XyZ9876._adb-tls-connect._tcp，取中间可辨识部分
                short = re.sub(r"^adb-", "", serial)
                short = re.sub(r"\._adb.*$", "", short)
                if len(short) > 22:
                    short = short[:22] + "…"
            tag = "" if state == "device" else "  [%s]" % state
            label = "%s ｜ %s ｜ %s%s" % (model or "未知机型", short, kind, tag)
            while label in self._dev_map:
                label += " "
            self._dev_map[label] = serial
            labels.append(label)
        self.cmb_dev["values"] = labels

        if ready:
            self.cmb_dev.current(0)
            serial, state, model, kind = ready[0]
            self.serial = serial
            self.log("检测到设备：%s（%s，%s连接）" % (model or serial, serial, kind), "ok")
            self.lbl_dev.configure(text="状态：已连接 %s" % (model or ""), style="Ok.TLabel")
            self.check_app(silent=True)
        else:
            self.serial = None
            self.lbl_dev.configure(text="状态：未连接", style="Bad.TLabel")
            self.lbl_pkg.configure(text="状态：未检测", style="Sub.TLabel")
            if items:
                self.log("设备已发现但状态异常（未授权/离线），请在手机上点「允许USB调试」", "warn")
                for serial, state, model, kind in items:
                    self.log("  %s → %s" % (serial, state), "warn")
            else:
                self.log("未检测到设备：请用数据线连接，或先在手机上开启「无线调试」后点「自动发现」", "warn")

    def wifi_discover(self):
        self.bg(self._wifi_discover)

    def _wifi_discover(self):
        self.log("正在扫描局域网内的无线调试设备…", "cmd")
        rc, out = run_adb(["mdns", "services"], timeout=20)
        found = []
        for l in out.splitlines():
            if "_adb-tls-connect._tcp" in l or "_adb._tcp" in l:
                parts = l.split()
                if len(parts) >= 2:
                    found.append(parts[0] if parts[0].startswith("adb-") else parts[-1])
        # 兼容不同输出格式，直接抓 ip:port
        addrs = re.findall(r"(\d{1,3}(?:\.\d{1,3}){3}:\d{2,5})", out)
        if not found and not addrs:
            self.log("未发现无线调试服务。请确认手机与电脑在同一 WiFi，且已开启「无线调试」。", "warn")
            return
        targets = addrs or found
        for t in set(targets):
            self.log("尝试连接 %s …" % t, "cmd")
            rc, o = run_adb(["connect", t], timeout=20)
            self.log("  %s" % o.strip().replace("\n", " "), "ok" if "connected" in o else "warn")
        self._refresh_devices()

    def wifi_connect(self):
        addr = self.ent_ip.get().strip()
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d{2,5}$", addr):
            messagebox.showwarning("地址格式不对", "请填写 IP:端口，例如 192.168.1.100:5555")
            return
        self.bg(self._wifi_connect, addr)

    def _wifi_connect(self, addr):
        self.log("连接 %s …" % addr, "cmd")
        rc, out = run_adb(["connect", addr], timeout=20)
        self.log(out.strip(), "ok" if "connected" in out else "err")
        self._refresh_devices()

    # ------------------------------------------------------------ 应用
    def check_app(self, silent=False):
        if self.busy and not silent:
            return
        if silent:
            threading.Thread(target=self._check_app, args=(silent,), daemon=True).start()
        else:
            self.bg(self._check_app, silent)

    def _check_app(self, silent=False):
        pkg = self.cmb_pkg.get().strip()
        if not pkg:
            return
        if DEMO:
            self.root.after(0, lambda: self.lbl_pkg.configure(
                text="状态：已安装  3.0.1-20260313", style="Ok.TLabel"))
            self.log("「%s」已安装，版本 3.0.1-20260313" % pkg, "ok")
            self.log("  安装位置：/system/priv-app/SystemHelper/SystemHelper.apk")
            self.log("  特权应用（priv-app），需用 --user 0 方式卸载", "warn")
            return
        if not self.serial:
            if not silent:
                self.log("没有可用设备", "err")
            return

        rc, out = run_adb(["shell", "pm", "path", pkg], serial=self.serial, timeout=30)
        installed = "package:" in out

        if not installed:
            self.root.after(0, lambda: self.lbl_pkg.configure(
                text="状态：未安装（已移除或本就不存在）", style="Bad.TLabel"))
            self.log("「%s」未安装" % pkg, "warn")
            return

        path = re.search(r"package:(.+)", out)
        path = path.group(1).strip() if path else ""

        rc, d = run_adb(["shell", "dumpsys", "package", pkg], serial=self.serial, timeout=30)
        ver = re.search(r"versionName=(\S+)", d)
        ver = ver.group(1) if ver else "?"
        is_sys = "/system" in path or "/product" in path or "SYSTEM" in d
        priv = "/priv-app/" in path

        info = "状态：已安装  %s" % ver
        self.root.after(0, lambda: self.lbl_pkg.configure(text=info, style="Ok.TLabel"))
        self.log("「%s」已安装，版本 %s" % (pkg, ver), "ok")
        self.log("  安装位置：%s" % (path or "未知"))
        if priv:
            self.log("  特权应用（priv-app），需用 --user 0 方式卸载", "warn")
        elif is_sys:
            self.log("  系统应用", "warn")

    def uninstall_app(self):
        pkg = self.cmb_pkg.get().strip()
        if not pkg:
            messagebox.showwarning("缺少包名", "请先填写要卸载的包名")
            return
        if pkg in PROTECTED_PKGS:
            messagebox.showerror(
                "已阻止",
                "「%s」属于系统核心组件，卸载会导致手机无法正常使用。\n本工具已拒绝该操作。" % pkg,
            )
            self.log("拒绝卸载受保护的核心组件：%s" % pkg, "err")
            return
        if not self.serial:
            messagebox.showwarning("未连接设备", "请先连接手机并确认已授权调试")
            return
        if not messagebox.askyesno(
            "确认卸载",
            "即将从手机卸载：\n\n%s\n\n采用 pm uninstall --user 0，可随时恢复。\n是否继续？" % pkg,
        ):
            return
        self.bg(self._uninstall_app, pkg)

    def _uninstall_app(self, pkg):
        # 1) 先检测
        rc, out = run_adb(["shell", "pm", "path", pkg], serial=self.serial, timeout=30)
        if "package:" not in out:
            self.log("「%s」本来就没装，无需卸载" % pkg, "warn")
            self.root.after(0, lambda: self.lbl_pkg.configure(
                text="状态：未安装", style="Bad.TLabel"))
            return
        apk_path = re.search(r"package:(.+)", out).group(1).strip()

        # 2) 备份
        if self.chk_backup.get():
            try:
                stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                safe = pkg.replace(".", "_")
                bdir = os.path.join(self.backup_root, "MI卸载备份_%s" % stamp)
                os.makedirs(bdir, exist_ok=True)
                self.log("备份 APK → %s" % bdir, "cmd")
                rc, o = run_adb(["pull", apk_path, os.path.join(bdir, "%s.apk" % safe)],
                                serial=self.serial, timeout=120)
                self.log("  " + (o.strip().replace("\n", " ") or "完成"), "ok" if rc == 0 else "err")
                # 顺带存一份安装态快照，恢复时对照
                rc2, d = run_adb(["dumpsys", "package", pkg], serial=self.serial, timeout=30)
                with open(os.path.join(bdir, "package_info.txt"), "w", encoding="utf-8") as f:
                    f.write("包名：%s\nAPK 路径：%s\n备份时间：%s\n\n%s"
                            % (pkg, apk_path, stamp, d))
                self.log("  已保存 package_info.txt 快照", "ok")
            except Exception as e:
                if not messagebox.askyesno("备份失败", "备份出错：%s\n\n仍要继续卸载吗？" % e):
                    self.log("用户取消卸载", "warn")
                    return

        # 3) 卸载
        self.log("执行：pm uninstall --user 0 %s" % pkg, "cmd")
        rc, out = run_adb(["shell", "pm", "uninstall", "--user", "0", pkg],
                          serial=self.serial, timeout=90)
        ok = "Success" in out
        self.log("  " + out.strip(), "ok" if ok else "err")

        if ok:
            self.log("卸载成功，正在校验…", "ok")
            rc, out2 = run_adb(["shell", "pm", "path", pkg], serial=self.serial, timeout=30)
            gone = "package:" not in out2
            self.log("  校验：%s" % ("已不在安装列表" if gone else "仍存在，请重试"), "ok" if gone else "err")
            self.root.after(0, lambda: self.lbl_pkg.configure(
                text="状态：已卸载" if gone else "状态：卸载失败",
                style="Ok.TLabel" if gone else "Bad.TLabel"))
            if gone:
                self.root.after(0, lambda: messagebox.showinfo(
                    "完成", "「%s」已卸载。\n\n需要恢复时点「恢复」按钮即可。" % pkg))
        else:
            self.log("卸载失败。若是 -25 错误，说明该应用被厂商锁定，需 Root。", "err")

    def restore_app(self):
        pkg = self.cmb_pkg.get().strip()
        if not pkg:
            return
        if not self.serial:
            messagebox.showwarning("未连接设备", "请先连接手机")
            return
        self.bg(self._restore_app, pkg)

    def _restore_app(self, pkg):
        self.log("执行：pm install-existing %s" % pkg, "cmd")
        rc, out = run_adb(["shell", "pm", "install-existing", pkg],
                          serial=self.serial, timeout=90)
        ok = "installed" in out.lower()
        self.log("  " + out.strip(), "ok" if ok else "err")
        if ok:
            self.log("已恢复「%s」" % pkg, "ok")
            self._check_app(silent=True)


# ---------------------------------------------------------------- 自检模式
def selftest():
    """无人值守自检：结果写到临时目录，同时打印到 stdout（GUI 程序无控制台时靠文件）"""
    log_path = os.path.join(tempfile.gettempdir(), "MiUninstaller_selftest.txt")
    lines = ["log_path: %s" % log_path]
    lines.append("adb found: %s" % ADB)
    lines.append("resource_dir: %s" % resource_dir())
    lines.append("frozen: %s" % getattr(sys, "frozen", False))
    if ADB:
        rc, out = run_adb(["version"])
        lines.append("adb version rc=%s\n%s" % (rc, out.strip()))
        rc, out = run_adb(["devices", "-l"])
        lines.append("devices rc=%s\n%s" % (rc, out.strip()))
        # 收掉 adb 守护进程，否则 CI 里 Start-Process 会一直等子进程退出
        run_adb(["kill-server"], timeout=15)
    lines.append("presets: %d" % len(PRESETS))
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))
    return 0


def main():
    if "--selftest" in sys.argv:
        return selftest()

    # 高 DPI 适配
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    try:
        base = resource_dir()
        ico = os.path.join(base, "app.ico")
        if os.path.isfile(ico):
            root.iconbitmap(ico)
    except Exception:
        pass
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
