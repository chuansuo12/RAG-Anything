#!/usr/bin/env python3
"""
批量获取解析结果脚本：根据 batch_id 查询 MinerU 解析状态并下载结果。

- 通过 GET https://mineru.net/api/v4/extract-results/batch/{batch_id} 查询状态
- 对 state=done 的任务下载 full_zip_url 到指定目录
- 可选从上传日志中解析 batch_id，或轮询直到全部完成后再下载
- 相关日志写入 download_yyyy-MM-dd-HHmmss.log

使用前请设置环境变量 MINERU_API_TOKEN。
文档：https://mineru.net/apiManage/docs
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("请安装 requests: pip install requests", file=sys.stderr)
    sys.exit(1)

EXTRACT_RESULTS_BATCH_URL = "https://mineru.net/api/v4/extract-results/batch"

# 任务状态：完成才有下载链接
STATE_DONE = "done"
STATE_TERMINAL_FAIL = "failed"


def get_batch_results(token: str, batch_id: str) -> requests.Response:
    """查询批量任务结果。"""
    url = f"{EXTRACT_RESULTS_BATCH_URL}/{batch_id}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    return requests.get(url, headers=headers, timeout=60)


def parse_batch_ids_from_upload_log(log_path: Path) -> list[str]:
    """从上传日志中解析出所有 batch_id（匹配「本批次 batch_id」下一行）。"""
    text = log_path.read_text(encoding="utf-8")
    ids: list[str] = []
    # 匹配 "### 本批次 batch_id（用于后续批量获取任务结果）" 下一行的 uuid
    for m in re.finditer(
        r"### 本批次 batch_id[^\n]*\n([a-fA-F0-9\-]{36})",
        text,
    ):
        bid = m.group(1).strip()
        if bid and bid not in ids:
            ids.append(bid)
    return ids


def download_file(url: str, dest_path: Path, timeout: int = 600) -> tuple[bool, str]:
    """下载文件到 dest_path，返回 (成功, 说明)。"""
    try:
        r = requests.get(url, stream=True, timeout=timeout)
        r.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True, ""
    except Exception as e:
        return False, str(e)


def run(
    batch_ids: list[str],
    output_dir: Path,
    log_dir: Path,
    token: str,
    poll_interval_sec: float | None = None,
    wait_until_done: bool = False,
) -> None:
    """根据 batch_id 查询状态并下载已完成的解析结果。"""
    if not batch_ids:
        print("未提供任何 batch_id")
        return

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir = log_dir.resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"download_{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.log"
    log_lines: list[str] = []
    log_lines.append("# MinerU 批量获取解析结果与下载日志")
    log_lines.append(f"# 开始时间: {datetime.now().isoformat()}")
    log_lines.append(f"# batch_id 数量: {len(batch_ids)}")
    log_lines.append(f"# 下载目录: {output_dir}")
    log_lines.append("")

    print(f"[MinerU 下载] 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[MinerU 下载] 待处理 batch 数: {len(batch_ids)}")
    print(f"[MinerU 下载] 下载目录: {output_dir}")
    print(f"[MinerU 下载] 日志文件: {log_path}")
    if wait_until_done and poll_interval_sec:
        print(f"[MinerU 下载] 轮询模式: 每 {poll_interval_sec}s 检查一次，直到全部完成或失败")
    print()

    total_downloaded = 0
    total_skipped = 0
    total_failed = 0
    poll_round = 0

    while True:
        all_done = True
        if wait_until_done and poll_interval_sec and poll_round > 0:
            print(f"[MinerU 下载] 轮询第 {poll_round} 轮，检查 {len(batch_ids)} 个 batch...")
        for idx, batch_id in enumerate(batch_ids):
            short_id = f"{batch_id[:8]}...{batch_id[-4:]}" if len(batch_id) > 16 else batch_id
            print(f"[MinerU 下载] 查询 batch {idx + 1}/{len(batch_ids)}: {short_id}")
            resp = get_batch_results(token, batch_id)
            try:
                result = resp.json()
            except Exception:
                result = {"_raw": resp.text, "_status_code": resp.status_code}

            log_lines.append(f"## batch_id: {batch_id}")
            log_lines.append(f"查询状态码: {resp.status_code}")
            log_lines.append(json.dumps(result, ensure_ascii=False, indent=2))
            log_lines.append("")

            if resp.status_code != 200 or result.get("code") != 0:
                print(f"  -> 查询失败 (HTTP {resp.status_code}), 跳过本批次")
                log_lines.append("查询失败，跳过本批次。")
                log_lines.append("")
                total_failed += 1
                continue

            data = result.get("data") or {}
            results_list = data.get("extract_result") or data.get("extract_results") or []
            if not isinstance(results_list, list):
                results_list = []

            n_done = sum(1 for it in results_list if (it or {}).get("state") == STATE_DONE)
            n_running = sum(1 for it in results_list if (it or {}).get("state") in ("pending", "running", "converting", "waiting-file"))
            n_fail = sum(1 for it in results_list if (it or {}).get("state") == STATE_TERMINAL_FAIL)
            print(f"  -> 共 {len(results_list)} 个任务: done={n_done}, 进行中={n_running}, failed={n_fail}")

            for item in results_list:
                state = (item or {}).get("state", "")
                file_name = (item or {}).get("file_name") or "unknown"
                if state != STATE_DONE:
                    all_done = False
                    if wait_until_done and poll_interval_sec and state not in (
                        STATE_TERMINAL_FAIL,
                    ):
                        continue
                    print(f"  - {file_name}: state={state}, 未下载")
                    log_lines.append(f"- {file_name}: state={state}, 未下载")
                    total_skipped += 1
                    continue
                zip_url = (item or {}).get("full_zip_url")
                if not zip_url:
                    print(f"  - {file_name}: state=done 但无下载链接, 跳过")
                    log_lines.append(f"- {file_name}: state=done 但无 full_zip_url, 未下载")
                    total_skipped += 1
                    continue
                # 保存到 output_dir/batch_id/ 下，文件名用原文件名或从 URL 取
                safe_name = Path(file_name).stem if file_name != "unknown" else ""
                if not safe_name:
                    safe_name = Path(urlparse(zip_url).path).stem or "result"
                dest_name = f"{safe_name}.zip"
                dest_path = output_dir / batch_id / dest_name
                print(f"  - 下载中: {file_name} -> {dest_path}")
                ok, err = download_file(zip_url, dest_path)
                if ok:
                    print(f"    已下载: {dest_path}")
                    log_lines.append(f"- {file_name}: 已下载 -> {dest_path}")
                    total_downloaded += 1
                else:
                    print(f"    下载失败: {err}")
                    log_lines.append(f"- {file_name}: 下载失败 {err}")
                    total_failed += 1

            log_lines.append("")

        if not wait_until_done or all_done or poll_interval_sec is None:
            break
        poll_round += 1
        print(f"\n[MinerU 下载] 仍有任务未完成，{poll_interval_sec}s 后重试...")
        log_lines.append(f"# 轮询等待 {poll_interval_sec}s 后重试...")
        log_lines.append("")
        time.sleep(poll_interval_sec)

    log_lines.append("## 汇总")
    log_lines.append(f"下载成功: {total_downloaded}")
    log_lines.append(f"未完成/跳过: {total_skipped}")
    log_lines.append(f"失败: {total_failed}")
    log_lines.append(f"# 结束时间: {datetime.now().isoformat()}")

    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    print()
    print("[MinerU 下载] ---------- 汇总 ----------")
    print(f"[MinerU 下载] 下载成功: {total_downloaded}")
    print(f"[MinerU 下载] 未完成/跳过: {total_skipped}")
    print(f"[MinerU 下载] 失败: {total_failed}")
    print(f"[MinerU 下载] 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[MinerU 下载] 日志已写入: {log_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="根据 batch_id 查询 MinerU 解析状态并下载结果到本地",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--batch-id",
        action="append",
        dest="batch_ids",
        default=[],
        help="可多次指定，每个 batch_id 查询并下载",
    )
    parser.add_argument(
        "--from-upload-log",
        type=Path,
        action="append",
        dest="from_upload_logs",
        default=None,
        metavar="PATH",
        help="从上传日志文件中解析 batch_id，可多次指定多个日志",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/Users/tengyujia/ml_data/MMLongBench-Doc/mineru-documents"),
        help="解析结果 zip 下载目录（按 batch_id 分子目录）",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("/Users/tengyujia/ml_data/MMLongBench-Doc"),
        help="下载日志输出目录（文件名: download_yyyy-MM-dd-HHmmss.log）",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=10,
        metavar="SECONDS",
        help="轮询间隔秒数；与 --wait-until-done 一起使用时，在未全部完成时每隔 N 秒再查一次",
    )
    parser.add_argument(
        "--wait-until-done",
        action="store_true",
        help="轮询直到所有任务为 done 或 failed 后再下载（需同时设置 --poll-interval）",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=os.environ.get("MINERU_API_TOKEN", ""),
        help="MinerU API Token（也可用环境变量 MINERU_API_TOKEN）",
    )
    args = parser.parse_args()

    batch_ids: list[str] = list(args.batch_ids)
    if args.from_upload_logs:
        for log_path in args.from_upload_logs:
            p = Path(log_path).resolve()
            if not p.is_file():
                print(f"错误: 上传日志不存在: {p}", file=sys.stderr)
                sys.exit(1)
            found = parse_batch_ids_from_upload_log(p)
            batch_ids.extend(found)
            print(f"[MinerU 下载] 从 {p.name} 解析到 {len(found)} 个 batch_id")
        batch_ids = list(dict.fromkeys(batch_ids))
        print(f"[MinerU 下载] 去重后共 {len(batch_ids)} 个 batch_id\n")

    if not batch_ids:
        print("错误: 未提供 batch_id。请使用 --batch-id 或 --from-upload-log", file=sys.stderr)
        sys.exit(1)
    if not args.token.strip():
        print("错误: 未设置 MINERU_API_TOKEN 或 --token", file=sys.stderr)
        sys.exit(1)
    if args.wait_until_done and (args.poll_interval is None or args.poll_interval <= 0):
        print("错误: --wait-until-done 需配合 --poll-interval SECONDS 使用", file=sys.stderr)
        sys.exit(1)

    run(
        batch_ids=batch_ids,
        output_dir=args.output_dir,
        log_dir=args.log_dir,
        token=args.token.strip(),
        poll_interval_sec=args.poll_interval,
        wait_until_done=args.wait_until_done,
    )


if __name__ == "__main__":
    main()
