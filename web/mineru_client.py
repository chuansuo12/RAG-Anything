from __future__ import annotations

import os
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import HTTPException

try:
    from config.api_keys import MINERU_API_TOKEN as CONFIG_MINERU_API_TOKEN
except Exception:  # noqa: BLE001
    CONFIG_MINERU_API_TOKEN = ""


FILE_URLS_BATCH_URL = "https://mineru.net/api/v4/file-urls/batch"
EXTRACT_RESULTS_BATCH_URL = "https://mineru.net/api/v4/extract-results/batch"
STATE_DONE = "done"
STATE_TERMINAL_FAIL = "failed"


def _get_mineru_token() -> str:
    # 优先使用 config.api_keys 中配置的 Token，其次环境变量
    token = (CONFIG_MINERU_API_TOKEN or os.environ.get("MINERU_API_TOKEN", "")).strip()
    if not token:
        raise HTTPException(
            status_code=500,
            detail="MinerU API Token 未配置，请设置环境变量 MINERU_API_TOKEN。",
        )
    return token


def _safe_extract(zip_path: Path, dest_dir: Path) -> List[Path]:
    """安全解压 zip，返回解压出的文件列表。"""
    extracted: List[Path] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename
            if ".." in name or name.startswith("/"):
                continue
            path = dest_dir / name
            if info.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(zf.read(info))
                extracted.append(path)
    return extracted


def _mineru_upload_and_download(
    pdf_path: Path,
    parsed_dir: Path,
    log_lines: List[str],
    max_wait_seconds: int = 600,
    poll_interval: int = 5,
) -> None:
    """
    调用 MinerU 云 API 完成 PDF 解析，并将结果 zip 解压到 parsed_dir。
    """
    token = _get_mineru_token()

    log_lines.append("步骤 1/3：向 MinerU 申请上传链接...")
    file_infos: List[Dict[str, Any]] = [
        {
            "name": pdf_path.name,
            "data_id": pdf_path.stem[:128].replace(" ", "_"),
        }
    ]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    data: Dict[str, Any] = {"files": file_infos, "model_version": "vlm"}
    resp = requests.post(FILE_URLS_BATCH_URL, headers=headers, json=data, timeout=60)
    try:
        result = resp.json()
    except Exception:
        result = {"_raw_text": resp.text, "_status_code": resp.status_code}

    if resp.status_code != 200 or result.get("code") != 0:
        raise RuntimeError(f"申请上传链接失败: HTTP {resp.status_code}, body={result}")

    data = result.get("data") or {}
    batch_id = data.get("batch_id", "")
    urls = data.get("file_urls") or data.get("files") or []
    if not urls:
        raise RuntimeError("MinerU 返回的上传链接为空。")
    upload_url = urls[0]
    log_lines.append(f"已获取 MinerU batch_id={batch_id}，开始上传文件...")

    with pdf_path.open("rb") as f:
        put_resp = requests.put(upload_url, data=f, timeout=300)
    if put_resp.status_code != 200:
        raise RuntimeError(f"上传文件到 MinerU 失败: HTTP {put_resp.status_code}, body={put_resp.text[:200]}")

    log_lines.append("上传完成，等待 MinerU 完成解析...")

    # 轮询解析结果
    start_ts = time.time()
    zip_url: Optional[str] = None

    while True:
        if time.time() - start_ts > max_wait_seconds:
            raise RuntimeError("等待 MinerU 解析超时，请稍后重试。")

        url = f"{EXTRACT_RESULTS_BATCH_URL}/{batch_id}"
        resp = requests.get(url, headers=headers, timeout=60)
        try:
            result = resp.json()
        except Exception:
            result = {"_raw": resp.text, "_status_code": resp.status_code}

        if resp.status_code != 200 or result.get("code") != 0:
            raise RuntimeError(f"查询 MinerU 解析状态失败: HTTP {resp.status_code}, body={result}")

        data = result.get("data") or {}
        results_list = data.get("extract_result") or data.get("extract_results") or []
        if not isinstance(results_list, list):
            results_list = []

        done_items = [it for it in results_list if (it or {}).get("state") == STATE_DONE]
        running_items = [
            it
            for it in results_list
            if (it or {}).get("state") in ("pending", "running", "converting", "waiting-file")
        ]
        failed_items = [it for it in results_list if (it or {}).get("state") == STATE_TERMINAL_FAIL]

        log_lines.append(
            f"MinerU 状态轮询：done={len(done_items)}, running={len(running_items)}, failed={len(failed_items)}"
        )

        if done_items:
            # 尝试按文件名匹配当前 pdf
            item = None
            for it in done_items:
                if (it or {}).get("file_name") == pdf_path.name:
                    item = it
                    break
            if item is None:
                item = done_items[0]

            zip_url = (item or {}).get("full_zip_url")
            if not zip_url:
                raise RuntimeError("MinerU 解析完成但未提供 full_zip_url。")
            break

        if failed_items and not running_items:
            raise RuntimeError("MinerU 解析任务失败，请检查 MinerU 控制台。")

        time.sleep(poll_interval)

    log_lines.append("解析完成，开始下载解析结果 zip...")

    parsed_dir.mkdir(parents=True, exist_ok=True)
    zip_path = parsed_dir / "mineru_result.zip"
    with requests.get(zip_url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with zip_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    _safe_extract(zip_path, parsed_dir)
    try:
        zip_path.unlink()
    except Exception:
        pass

    log_lines.append(f"解析结果已解压到: {parsed_dir}")

