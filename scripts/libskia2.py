#!/usr/bin/env python3
"""libskia2 构建驱动 —— Linux 与 Windows 共用一份实现。

子命令:
  sync     按 config/skia.pin 取回 Skia 源码与依赖，并拉取 gn / ninja
  gen      合并 GN args 写入 out/<target>/args.gn，执行 gn gen
  build    ninja 构建，并按产物清单逐个校验（缺一个即失败）
  package  打包静态库 + 头文件 + CMake package + key.txt + SHA256
  all      上述四步顺序执行

产物清单是硬校验：某个 GN arg 改动导致模块静默消失时，必须在这里就失败，
而不是等消费方链接时才发现。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIA = ROOT / "externals" / "skia"
CONFIG = ROOT / "config"

# Windows 上 Python 的 stdout 默认走 cp1252，输出中文会直接抛 UnicodeEncodeError。
# 必须在任何 log() 之前完成切换。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

TARGETS = ("linux-x64", "windows-x64-msvc")

# GN 目标 -> 产物基名。产物文件名在 Unix 上是 lib<name>.a，Windows 上是 <name>.lib。
# 依据 doc/gui-framework-profile.md §3.4。
BUILD_TARGETS = (
    "skia",
    "modules/skshaper",
    "modules/skparagraph",
    "modules/skunicode",
    "modules/svg",
    "modules/skresources",
)

EXPECTED_LIBS = (
    "skia",
    "skshaper",
    "skparagraph",
    "skunicode_core",
    "skunicode_libgrapheme",
    "svg",
    "skresources",
)


# --------------------------------------------------------------------------- 基础设施


def log(msg: str) -> None:
    print(f"[libskia2] {msg}", flush=True)


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
    log("$ " + " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, check=True)


def is_windows(target: str) -> bool:
    return target.startswith("windows")


def lib_filename(base: str, target: str) -> str:
    return f"{base}.lib" if is_windows(target) else f"lib{base}.a"


def read_pin() -> dict[str, str]:
    pin: dict[str, str] = {}
    for line in (CONFIG / "skia.pin").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        pin[key.strip()] = value.strip()
    missing = {"SKIA_REPO", "SKIA_REF", "SKIA_COMMIT"} - pin.keys()
    if missing:
        sys.exit(f"config/skia.pin 缺少字段: {sorted(missing)}")
    return pin


def read_args(path: Path) -> list[str]:
    """解析 .gn.args：每行一个 key=value，# 起始为注释。"""
    args: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            sys.exit(f"{path} 中无法解析的行: {raw!r}")
        args.append(line)
    return args


# --------------------------------------------------------------------------- MSVC 探测


def discover_msvc() -> list[str]:
    """探测 MSVC 与 Windows SDK 路径。

    Skia 对这四项不做任何自动探测（gn/BUILDCONFIG.gn 里默认是空串），
    而 gn/toolchain/BUILD.gn 用它们拼出
    $win_vc/Tools/MSVC/$win_toolchain_version/bin/HostX64/x64/cl.exe。
    路径是机器相关的，所以在这里探测注入，不写进版本库。
    """
    vswhere = Path(
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    ) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.exists():
        sys.exit(f"找不到 vswhere.exe: {vswhere}")

    vs_root = subprocess.run(
        [
            str(vswhere), "-latest", "-products", "*",
            "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-property", "installationPath",
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if not vs_root:
        sys.exit("vswhere 未找到带 C++ 工具链的 Visual Studio 安装")

    win_vc = Path(vs_root) / "VC"
    msvc_dir = win_vc / "Tools" / "MSVC"
    versions = sorted((d.name for d in msvc_dir.iterdir() if d.is_dir()))
    if not versions:
        sys.exit(f"{msvc_dir} 下没有 MSVC 工具链")
    toolchain_version = versions[-1]

    win_sdk = Path(os.environ.get("WindowsSdkDir", r"C:\Program Files (x86)\Windows Kits\10"))
    sdk_include = win_sdk / "Include"
    sdk_versions = sorted(
        d.name for d in sdk_include.iterdir() if d.is_dir() and d.name.startswith("10.")
    )
    if not sdk_versions:
        sys.exit(f"{sdk_include} 下没有 Windows SDK")
    sdk_version = sdk_versions[-1]

    log(f"MSVC {toolchain_version} @ {win_vc}")
    log(f"Windows SDK {sdk_version} @ {win_sdk}")

    # GN 的字符串值用正斜杠，反斜杠在 GN 里是转义字符。
    def gn_path(p: Path) -> str:
        return str(p).replace("\\", "/")

    return [
        f'win_vc="{gn_path(win_vc)}"',
        f'win_toolchain_version="{toolchain_version}"',
        f'win_sdk="{gn_path(win_sdk)}"',
        f'win_sdk_version="{sdk_version}"',
    ]


# --------------------------------------------------------------------------- sync


def cmd_sync(_target: str) -> None:
    pin = read_pin()
    SKIA.parent.mkdir(parents=True, exist_ok=True)

    if not (SKIA / ".git").exists():
        log(f"取回 Skia {pin['SKIA_REF']} @ {pin['SKIA_COMMIT'][:12]}")
        SKIA.mkdir(parents=True, exist_ok=True)
        run(["git", "init", "-q"], cwd=SKIA)
        run(["git", "remote", "add", "origin", pin["SKIA_REPO"]], cwd=SKIA)

    # 优先按 SHA 精确取，失败则退回按分支取（某些 git server 不允许 fetch 任意 SHA）。
    try:
        run(["git", "fetch", "--depth", "1", "origin", pin["SKIA_COMMIT"]], cwd=SKIA)
        run(["git", "checkout", "-q", "FETCH_HEAD"], cwd=SKIA)
    except subprocess.CalledProcessError:
        log("按 SHA fetch 失败，退回按分支取")
        run(["git", "fetch", "--depth", "1", "origin", pin["SKIA_REF"]], cwd=SKIA)
        run(["git", "checkout", "-q", "FETCH_HEAD"], cwd=SKIA)

    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=SKIA, capture_output=True, text=True, check=True
    ).stdout.strip()
    if actual != pin["SKIA_COMMIT"]:
        sys.exit(
            f"Skia commit 不符：\n  期望 {pin['SKIA_COMMIT']}\n  实际 {actual}\n"
            f"分支已前移。请更新 config/skia.pin 后重跑 —— 构建可复现不允许静默漂移。"
        )
    log(f"Skia commit 校验通过: {actual}")

    env = dict(os.environ, GIT_SYNC_DEPS_SKIP_EMSDK="true")
    run([sys.executable, "tools/git-sync-deps"], cwd=SKIA, env=env)
    run([sys.executable, "bin/fetch-gn"], cwd=SKIA)
    run([sys.executable, "bin/fetch-ninja"], cwd=SKIA)


# --------------------------------------------------------------------------- gen


def collect_args(target: str) -> list[str]:
    args = read_args(CONFIG / "common.gn.args")
    args += read_args(CONFIG / f"{target}.gn.args")
    if is_windows(target):
        args += discover_msvc()
    return args


def out_dir(target: str) -> Path:
    return SKIA / "out" / target


def gn_binary() -> Path:
    exe = SKIA / "bin" / ("gn.exe" if platform.system() == "Windows" else "gn")
    if not exe.exists():
        sys.exit(f"找不到 gn: {exe}，先跑 sync")
    return exe


def ninja_binary() -> Path:
    name = "ninja.exe" if platform.system() == "Windows" else "ninja"
    exe = SKIA / "third_party" / "ninja" / name
    if exe.exists():
        return exe
    fallback = shutil.which("ninja")
    if fallback:
        return Path(fallback)
    sys.exit("找不到 ninja，先跑 sync")


def cmd_gen(target: str) -> None:
    args = collect_args(target)
    out = out_dir(target)
    out.mkdir(parents=True, exist_ok=True)

    # 写 args.gn 而不是走 --args=：GN args 里含引号和方括号，
    # 在 Windows cmd 上做命令行转义极易出错，写文件没有这个问题。
    header = "# 由 scripts/libskia2.py 生成，勿手改。改 config/*.gn.args。\n"
    (out / "args.gn").write_text(header + "\n".join(args) + "\n", encoding="utf-8")
    log(f"写入 {out / 'args.gn'}（{len(args)} 条 args）")

    run([gn_binary(), "gen", out.relative_to(SKIA).as_posix()], cwd=SKIA)


# --------------------------------------------------------------------------- build


def cmd_build(target: str) -> None:
    out = out_dir(target)
    if not (out / "args.gn").exists():
        sys.exit(f"{out} 未配置，先跑 gen")

    run([ninja_binary(), "-C", out.relative_to(SKIA).as_posix(), *BUILD_TARGETS], cwd=SKIA)

    missing = [
        name for name in EXPECTED_LIBS
        if not (out / lib_filename(name, target)).exists()
    ]
    if missing:
        produced = sorted(p.name for p in out.glob("*.a")) + sorted(p.name for p in out.glob("*.lib"))
        sys.exit(
            "产物清单校验失败，缺少: "
            + ", ".join(lib_filename(m, target) for m in missing)
            + f"\n实际产出: {produced}\n"
            "某个 GN arg 让模块静默消失了。这里必须失败，不能留到消费方链接时才发现。"
        )
    for name in EXPECTED_LIBS:
        path = out / lib_filename(name, target)
        log(f"OK {path.name}  {path.stat().st_size / 1048576:.1f} MiB")


# --------------------------------------------------------------------------- package


def copy_headers(dest: Path) -> int:
    """复制头文件。

    保留相对 Skia 根目录的结构：Skia 的公开头之间是用
    `#include "include/core/SkCanvas.h"` 这种根相对路径互相引用的，
    所以消费方的 include path 必须指向这个根目录。

    不去猜"最小头文件集"——直接把 include/ 与全部 src、modules 下的 .h 都带上。
    代价是 tarball 里多几 MB 纯文本，换来的是彻底消除"漏头文件"这一整类失败。
    """
    count = 0

    def copy_tree(rel: str, pattern: str | None = None) -> None:
        nonlocal count
        src_root = SKIA / rel
        if not src_root.exists():
            return
        for src in src_root.rglob(pattern or "*"):
            if not src.is_file():
                continue
            if pattern is None and src.suffix not in (".h", ".hpp", ".inc", ".modulemap"):
                continue
            out_path = dest / src.relative_to(SKIA)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out_path)
            count += 1

    copy_tree("include")
    copy_tree("modules")
    copy_tree("src")
    return count


def cmd_package(target: str) -> None:
    version = os.environ.get("LIBSKIA2_VERSION", "0.0.0-dev")
    pin = read_pin()
    out = out_dir(target)
    stage = ROOT / "dist" / f"libskia2-{version}-{target}"

    if stage.exists():
        shutil.rmtree(stage)
    (stage / "lib").mkdir(parents=True)
    (stage / "include").mkdir(parents=True)
    (stage / "lib" / "cmake" / "skia2").mkdir(parents=True)

    for name in EXPECTED_LIBS:
        src = out / lib_filename(name, target)
        if not src.exists():
            sys.exit(f"缺少产物 {src}，先跑 build")
        shutil.copy2(src, stage / "lib" / src.name)
    log(f"复制 {len(EXPECTED_LIBS)} 个静态库")

    n = copy_headers(stage / "include" / "skia")
    log(f"复制 {n} 个头文件")

    shutil.copy2(SKIA / "LICENSE", stage / "LICENSE_SKIA")

    # CMake package：把链接顺序与 ABI 约束固化进去，消费方只写一行 target_link_libraries。
    template = (ROOT / "cmake" / "skia2Config.cmake.in").read_text(encoding="utf-8")
    (stage / "lib" / "cmake" / "skia2" / "skia2Config.cmake").write_text(
        template.replace("@LIBSKIA2_VERSION@", version).replace("@LIBSKIA2_TARGET@", target),
        encoding="utf-8",
    )

    # key.txt：gn args 指纹。光校验二进制不够，消费方要能确认"这个库到底开了什么"。
    # 只记录版本库里的 args —— MSVC 探测出来的路径是机器相关的，进指纹会破坏可比性。
    args = read_args(CONFIG / "common.gn.args") + read_args(CONFIG / f"{target}.gn.args")
    key = "\n".join(
        [
            f"libskia2_version={version}",
            f"target={target}",
            f"skia_repo={pin['SKIA_REPO']}",
            f"skia_ref={pin['SKIA_REF']}",
            f"skia_commit={pin['SKIA_COMMIT']}",
            "",
            "# gn args",
            *sorted(args),
        ]
    )
    (stage / "key.txt").write_text(key + "\n", encoding="utf-8")

    tarball = ROOT / "dist" / f"libskia2-{version}-{target}.tar.gz"
    with tarfile.open(tarball, "w:gz") as tf:
        tf.add(stage, arcname=stage.name)

    digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
    (tarball.parent / (tarball.name + ".sha256")).write_text(
        f"{digest}  {tarball.name}\n", encoding="utf-8"
    )
    log(f"{tarball.name}  {tarball.stat().st_size / 1048576:.1f} MiB")
    log(f"sha256 {digest}")


# --------------------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(description="libskia2 构建驱动")
    parser.add_argument("command", choices=("sync", "gen", "build", "package", "all"))
    parser.add_argument(
        "--target", required=True, choices=TARGETS, help="构建目标三元组"
    )
    ns = parser.parse_args()

    host = platform.system()
    if is_windows(ns.target) and host != "Windows":
        sys.exit(f"{ns.target} 需要在 Windows 上构建，当前是 {host}")
    if not is_windows(ns.target) and host == "Windows":
        sys.exit(f"{ns.target} 不能在 Windows 上构建")

    steps = {
        "sync": [cmd_sync],
        "gen": [cmd_gen],
        "build": [cmd_build],
        "package": [cmd_package],
        "all": [cmd_sync, cmd_gen, cmd_build, cmd_package],
    }[ns.command]

    for step in steps:
        step(ns.target)


if __name__ == "__main__":
    main()
