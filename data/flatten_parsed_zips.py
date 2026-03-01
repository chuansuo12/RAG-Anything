#!/usr/bin/env python3
"""
将 MinerU 下载的 zip（含 batch_id 子目录）解压到扁平目录：parsed-documents/文件名称/相关文件。

- 扫描源目录下所有 .zip（忽略中间的 batch_id 层级）
- 解压到目标目录下以「文件名称」命名的子目录，即 目标/文件名称/zip 内文件
- 若同名已存在则使用 文件名称_2、文件名称_3 等避免覆盖
"""

from __future__ import annotations

import argparse
import zipfile
from datetime import datetime
from pathlib import Path


def safe_extract(zip_path: Path, dest_dir: Path) -> list[Path]:
    """解压 zip 到 dest_dir，防止 zip slip，返回解压出的文件列表。"""
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            # 避免路径穿越
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


def run(
    source_dir: Path,
    target_dir: Path,
    dry_run: bool = False,
) -> None:
    """扫描 source_dir 下所有 zip，解压到 target_dir/文件名称/。"""
    source_dir = source_dir.resolve()
    target_dir = target_dir.resolve()
    if not source_dir.is_dir():
        print(f"错误: 源目录不存在: {source_dir}")
        return

    zips = list(source_dir.rglob("*.zip"))
    if not zips:
        print(f"[扁平解压] 在 {source_dir} 下未找到 .zip 文件")
        return

    print(f"[扁平解压] 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[扁平解压] 源目录: {source_dir}")
    print(f"[扁平解压] 目标目录: {target_dir}")
    print(f"[扁平解压] 找到 {len(zips)} 个 zip 文件")
    if dry_run:
        print("[扁平解压] 当前为 dry-run，仅列出将执行的操作，不实际解压")
    print()

    target_dir.mkdir(parents=True, exist_ok=True)
    used_stems: dict[str, int] = {}
    total_files = 0
    errors: list[tuple[Path, str]] = []

    for idx, zip_path in enumerate(sorted(zips), 1):
        stem = zip_path.stem
        if stem in used_stems:
            used_stems[stem] += 1
            folder_name = f"{stem}_{used_stems[stem]}"
        else:
            used_stems[stem] = 1
            folder_name = stem
        dest_root = target_dir / folder_name
        print(f"[扁平解压] ({idx}/{len(zips)}) {zip_path.relative_to(source_dir)} -> {dest_root}/")

        if dry_run:
            continue
        try:
            count = len(safe_extract(zip_path, dest_root))
            total_files += count
            print(f"  -> 已解压 {count} 个文件到 {dest_root}/")
        except zipfile.BadZipFile as e:
            errors.append((zip_path, str(e)))
            print(f"  -> 跳过（无效 zip）: {e}")
        except Exception as e:
            errors.append((zip_path, str(e)))
            print(f"  -> 失败: {e}")

    print()
    print("[扁平解压] ---------- 汇总 ----------")
    print(f"[扁平解压] 处理 zip 数: {len(zips)}")
    if not dry_run:
        print(f"[扁平解压] 解压出的文件总数: {total_files}")
        if errors:
            print(f"[扁平解压] 失败/跳过: {len(errors)}")
            for zp, msg in errors:
                print(f"  - {zp}: {msg}")
    print(f"[扁平解压] 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="将下载的 zip 解压到 目标/文件名称/ 的扁平目录，忽略 batch_id 层级",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path("/Users/tengyujia/ml_data/MMLongBench-Doc/mineru-documents"),
        help="存放 zip 的目录（可含 batch_id 子目录）",
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=Path("/Users/tengyujia/ml_data/MMLongBench-Doc/paresed-documents"),
        help="解压目标目录，结构为 目标/文件名称/相关文件",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅列出将要解压的 zip 与目标路径，不实际解压",
    )
    args = parser.parse_args()
    run(
        source_dir=args.source_dir,
        target_dir=args.target_dir,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
