#!/usr/bin/env python3
"""
综合脚本：按顺序执行 upload -> download -> parsed（扁平解压）。

通过指定一个根路径，统一派生各目录：
- 根路径/documents         -> 待上传文件（upload 源）
- 根路径/mineru-documents  -> 下载的 zip 存放目录（download 目标）
- 根路径/paresed-documents -> 解压后的扁平目录（parsed 目标）
- 根路径/                  -> upload_*.log 与 download_*.log 的存放目录
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# 本脚本所在目录，即 data/
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = Path("/Users/tengyujia/ml_data/MMLongBench-Doc")


def get_latest_upload_log(log_dir: Path) -> Path | None:
    """返回 log_dir 下最新的 upload_*.log，按修改时间。"""
    log_dir = log_dir.resolve()
    if not log_dir.is_dir():
        return None
    logs = sorted(
        log_dir.glob("upload_*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return logs[0] if logs else None


def run_cmd(args: list[str], step_name: str) -> int:
    """执行命令，打印步骤名与参数，返回 exit code。"""
    print(f"\n[综合脚本] ========== {step_name} ==========")
    print(f"[综合脚本] 执行: {' '.join(args)}")
    print()
    ret = subprocess.run(args)
    return ret.returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        description="顺序执行 upload -> download -> parsed，通过根路径统一指定各目录",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="根路径；其下使用 documents、mineru-documents、paresed-documents 及日志目录",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="跳过上传，仅执行 download + parsed（需已有 upload 日志或本次用 --upload-log 指定）",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="跳过下载，仅执行 upload + parsed（使用已有 mineru-documents）",
    )
    parser.add_argument(
        "--skip-parsed",
        action="store_true",
        help="跳过扁平解压，仅执行 upload + download",
    )
    parser.add_argument(
        "--upload-log",
        type=Path,
        default=None,
        metavar="PATH",
        help="download 阶段使用的上传日志；未指定时使用根路径下最新的 upload_*.log",
    )
    parser.add_argument(
        "--wait-until-done",
        action="store_true",
        help="download 阶段轮询直到全部解析完成再下载",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=60,
        metavar="SECONDS",
        help="download 轮询间隔（与 --wait-until-done 一起使用）",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="upload 阶段不递归子目录",
    )
    parser.add_argument(
        "--token",
        type=str,
        default="",
        help="MinerU API Token；未指定时使用环境变量 MINERU_API_TOKEN",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    documents_dir = root / "documents"
    mineru_documents_dir = root / "mineru-documents"
    parsed_dir = root / "paresed-documents"
    log_dir = root

    import os
    token = (args.token or os.environ.get("MINERU_API_TOKEN") or "eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiI0ODUwMDQ1OCIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc3MjM2MTQwNywiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiIiwib3BlbklkIjpudWxsLCJ1dWlkIjoiODQ1Y2RjOTEtOWZmNC00Nzg1LWFjYzItYzNjZGIyY2JhNGEwIiwiZW1haWwiOiIiLCJleHAiOjE3ODAxMzc0MDd9.6NreXyEjGwHQbhJCj4Nf3QcHk1wA0Eub8YHJHDEvUqQ9t-Ij_dqei9uXRnQUn0Po2eXLkWGPmTH45STnsvYwUQ").strip()
    if not args.skip_upload and not token:
        print("错误: 未设置 MINERU_API_TOKEN 或 --token，upload 需要 Token", file=sys.stderr)
        sys.exit(1)
    if not args.skip_download and not token:
        print("错误: 未设置 MINERU_API_TOKEN 或 --token，download 需要 Token", file=sys.stderr)
        sys.exit(1)

    print("[综合脚本] 根路径:", root)
    print("[综合脚本] documents_dir:", documents_dir)
    print("[综合脚本] mineru_documents_dir:", mineru_documents_dir)
    print("[综合脚本] parsed_dir:", parsed_dir)
    print("[综合脚本] log_dir:", log_dir)

    # 1. Upload
    if not args.skip_upload:
        upload_script = SCRIPT_DIR / "batch_upload_mineru.py"
        cmd = [
            sys.executable,
            str(upload_script),
            "--documents-dir", str(documents_dir),
            "--log-dir", str(log_dir),
        ]
        if args.no_recursive:
            cmd.append("--no-recursive")
        if token:
            cmd.extend(["--token", token])
        code = run_cmd(cmd, "1. Upload")
        if code != 0:
            print(f"[综合脚本] Upload 退出码 {code}，终止后续步骤")
            sys.exit(code)

    # 2. Download
    if not args.skip_download:
        upload_log = args.upload_log
        if upload_log is None:
            upload_log = get_latest_upload_log(log_dir)
        if upload_log is None or not Path(upload_log).resolve().is_file():
            print("[综合脚本] 未找到上传日志，请指定 --upload-log 或先执行 upload")
            sys.exit(1)
        upload_log = Path(upload_log).resolve()
        print(f"[综合脚本] 使用上传日志: {upload_log}")

        download_script = SCRIPT_DIR / "batch_download_mineru.py"
        cmd = [
            sys.executable,
            str(download_script),
            "--from-upload-log", str(upload_log),
            "--output-dir", str(mineru_documents_dir),
            "--log-dir", str(log_dir),
            "--poll-interval", str(args.poll_interval),
        ]
        if args.wait_until_done:
            cmd.append("--wait-until-done")
        if token:
            cmd.extend(["--token", token])
        code = run_cmd(cmd, "2. Download")
        if code != 0:
            print(f"[综合脚本] Download 退出码 {code}，终止后续步骤")
            sys.exit(code)

    # 3. Parsed (flatten)
    if not args.skip_parsed:
        flatten_script = SCRIPT_DIR / "flatten_parsed_zips.py"
        cmd = [
            sys.executable,
            str(flatten_script),
            "--source-dir", str(mineru_documents_dir),
            "--target-dir", str(parsed_dir),
        ]
        code = run_cmd(cmd, "3. Parsed（扁平解压）")
        if code != 0:
            print(f"[综合脚本] Parsed 退出码 {code}")
            sys.exit(code)

    print()
    print("[综合脚本] 全部步骤已完成")


if __name__ == "__main__":
    main()
