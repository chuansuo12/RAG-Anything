#!/usr/bin/env python
"""
将 parquet 文件转换为 CSV，方便查看和分析。

默认示例：
  python eval/parquet_to_csv.py runtime/eval/train-00000-of-00001.parquet
  -> 输出 runtime/eval/train-00000-of-00001.csv
"""

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(
        description="将 parquet 文件转换为 CSV",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "input_path",
        type=str,
        help="输入的 parquet 文件路径",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出 CSV 路径（默认与输入同名但后缀为 .csv）",
    )
    parser.add_argument(
        "--index",
        action="store_true",
        help="是否在 CSV 中保留行索引（默认不保留）",
    )

    args = parser.parse_args()

    input_path = Path(args.input_path)
    if not input_path.exists():
        print(f"错误: 输入文件不存在: {input_path}")
        return

    if args.output is None:
        output_path = input_path.with_suffix(".csv")
    else:
        output_path = Path(args.output)

    print(f"正在从 parquet 读取数据: {input_path}")
    try:
        df = pd.read_parquet(input_path)
    except Exception as e:  # noqa: BLE001
        print(f"读取 parquet 文件失败: {e}")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"正在写出 CSV: {output_path}")
    try:
        df.to_csv(output_path, index=args.index)
    except Exception as e:  # noqa: BLE001
        print(f"写 CSV 文件失败: {e}")
        return

    print(f"转换完成: {input_path} -> {output_path}")


if __name__ == "__main__":
    main()

