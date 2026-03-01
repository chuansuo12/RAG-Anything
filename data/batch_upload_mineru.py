#!/usr/bin/env python3
"""
批量上传脚本：使用 MinerU「文件批量上传解析」API 上传本地文件。

- 从指定目录读取支持的文件（pdf、doc、docx、ppt、pptx、png、jpg、jpeg、html）
- 调用 https://mineru.net/api/v4/file-urls/batch 批量申请上传链接
- 将文件 PUT 到返回的链接，上传完成后 MinerU 会自动提交解析任务
- 将每次申请与上传的 response 写入日志，便于后续用 batch_id 获取解析结果

使用前请在官网申请 API Token，并设置环境变量 MINERU_API_TOKEN。
文档：https://mineru.net/apiManage/docs
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("请安装 requests: pip install requests", file=sys.stderr)
    sys.exit(1)

# MinerU 文件批量上传解析 API
FILE_URLS_BATCH_URL = "https://mineru.net/api/v4/file-urls/batch"

# 支持的后缀（与 API 文档一致）
SUPPORTED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".html",
}

# 单次申请链接上限（API 限制）
MAX_FILES_PER_BATCH = 200


def collect_files(documents_dir: Path, recursive: bool) -> list[Path]:
    """收集目录下支持的文件。"""
    documents_dir = documents_dir.resolve()
    if not documents_dir.is_dir():
        raise FileNotFoundError(f"目录不存在: {documents_dir}")
    out: list[Path] = []
    if recursive:
        for p in documents_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                out.append(p)
    else:
        for p in documents_dir.iterdir():
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                out.append(p)
    return sorted(out)


def choose_model_version(files: list[Path]) -> str:
    """若全部为 html 则用 MinerU-HTML，否则用 vlm。"""
    if not files:
        return "vlm"
    if all(p.suffix.lower() == ".html" for p in files):
        return "MinerU-HTML"
    return "vlm"


def apply_upload_urls(
    token: str,
    file_infos: list[dict],
    model_version: str,
) -> requests.Response:
    """申请批量上传链接。"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    data = {
        "files": file_infos,
        "model_version": model_version,
    }
    return requests.post(FILE_URLS_BATCH_URL, headers=headers, json=data, timeout=60)


def upload_file_to_url(file_path: Path, upload_url: str) -> tuple[int, str]:
    """将本地文件 PUT 到上传链接。上传时无须设置 Content-Type。"""
    with open(file_path, "rb") as f:
        r = requests.put(upload_url, data=f, timeout=300)
    return r.status_code, r.text or ""


def run(
    documents_dir: Path,
    log_dir: Path,
    token: str,
    recursive: bool = True,
    batch_size: int = MAX_FILES_PER_BATCH,
) -> None:
    """扫描目录、分批申请链接、上传并写日志。"""
    files = collect_files(documents_dir, recursive)
    if not files:
        print(f"在 {documents_dir} 下未找到支持的文件（{SUPPORTED_EXTENSIONS}）")
        return

    log_dir = log_dir.resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"upload_{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.log"
    log_lines: list[str] = []
    log_lines.append(f"# MinerU 文件批量上传解析日志")
    log_lines.append(f"# 文档目录: {documents_dir}")
    log_lines.append(f"# 开始时间: {datetime.now().isoformat()}")
    log_lines.append(f"# 文件总数: {len(files)}")
    log_lines.append("")

    total_upload_ok = 0
    total_upload_fail = 0
    batches = [
        files[i : i + batch_size]
        for i in range(0, len(files), batch_size)
    ]

    for batch_idx, batch_files in enumerate(batches):
        model_version = choose_model_version(batch_files)
        file_infos = [
            {"name": p.name, "data_id": p.stem[:128].replace(" ", "_")}
            for p in batch_files
        ]
        log_lines.append(f"## Batch {batch_idx + 1}/{len(batches)} (共 {len(batch_files)} 个文件)")
        log_lines.append(f"model_version: {model_version}")
        log_lines.append("")

        resp = apply_upload_urls(token, file_infos, model_version)
        try:
            result = resp.json()
        except Exception:
            result = {"_raw_text": resp.text, "_status_code": resp.status_code}
        log_lines.append("### 申请上传链接 Response")
        log_lines.append(json.dumps({"status_code": resp.status_code, "body": result}, ensure_ascii=False, indent=2))
        log_lines.append("")

        if resp.status_code != 200 or result.get("code") != 0:
            log_lines.append("申请链接失败，本批次跳过上传。")
            log_lines.append("")
            total_upload_fail += len(batch_files)
            continue

        data = result.get("data") or {}
        batch_id = data.get("batch_id", "")
        # API 返回字段可能是 file_urls 或 files
        urls = data.get("file_urls") or data.get("files") or []
        log_lines.append(f"batch_id: {batch_id}")
        log_lines.append("")

        if len(urls) != len(batch_files):
            log_lines.append(f"警告: 返回链接数({len(urls)})与文件数({len(batch_files)})不一致")
            log_lines.append("")

        upload_results = []
        for i, (path, url) in enumerate(zip(batch_files, urls)):
            status_code, body = upload_file_to_url(path, url)
            ok = status_code == 200
            if ok:
                total_upload_ok += 1
            else:
                total_upload_fail += 1
            upload_results.append({
                "path": str(path),
                "name": path.name,
                "url": url,
                "status_code": status_code,
                "success": ok,
                "response_preview": (body[:200] + "..." if len(body) > 200 else body),
            })
        log_lines.append("### 本批次上传结果")
        log_lines.append(json.dumps(upload_results, ensure_ascii=False, indent=2))
        log_lines.append("")
        # 便于后续脚本解析：每批次记录 batch_id 与文件对应关系
        log_lines.append(f"### 本批次 batch_id（用于后续批量获取任务结果）")
        log_lines.append(batch_id)
        log_lines.append("")
        print(f"Batch {batch_idx + 1}: batch_id={batch_id}, 上传成功={sum(1 for u in upload_results if u['success'])}, 失败={sum(1 for u in upload_results if not u['success'])}")

    log_lines.append("## 汇总")
    log_lines.append(f"上传成功: {total_upload_ok}")
    log_lines.append(f"上传失败: {total_upload_fail}")
    log_lines.append(f"# 结束时间: {datetime.now().isoformat()}")

    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"日志已写入: {log_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="使用 MinerU 文件批量上传解析 API 上传本地文件，并写 response 到日志",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--documents-dir",
        type=Path,
        default=Path("/Users/tengyujia/ml_data/MMLongBench-Doc/documents"),
        help="待上传文件所在目录",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("/Users/tengyujia/ml_data/MMLongBench-Doc"),
        help="上传日志输出目录（日志文件名: upload_yyyy-MM-dd-HHmmss.log）",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="不递归子目录，仅扫描顶层",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=MAX_FILES_PER_BATCH,
        help=f"每批申请上传链接的数量（API 单次最多 {MAX_FILES_PER_BATCH}）",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=os.environ.get("MINERU_API_TOKEN", "eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiI0ODUwMDQ1OCIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc3MjM2MTQwNywiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiIiwib3BlbklkIjpudWxsLCJ1dWlkIjoiODQ1Y2RjOTEtOWZmNC00Nzg1LWFjYzItYzNjZGIyY2JhNGEwIiwiZW1haWwiOiIiLCJleHAiOjE3ODAxMzc0MDd9.6NreXyEjGwHQbhJCj4Nf3QcHk1wA0Eub8YHJHDEvUqQ9t-Ij_dqei9uXRnQUn0Po2eXLkWGPmTH45STnsvYwUQ"),
        help="MinerU API Token（也可用环境变量 MINERU_API_TOKEN）",
    )
    args = parser.parse_args()

    if not args.token.strip():
        print("错误: 未设置 MinerU API Token。请设置环境变量 MINERU_API_TOKEN 或使用 --token", file=sys.stderr)
        sys.exit(1)
    if args.batch_size < 1 or args.batch_size > MAX_FILES_PER_BATCH:
        print(f"错误: --batch-size 须在 1 ～ {MAX_FILES_PER_BATCH} 之间", file=sys.stderr)
        sys.exit(1)

    run(
        documents_dir=args.documents_dir,
        log_dir=args.log_dir,
        token=args.token.strip(),
        recursive=not args.no_recursive,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
