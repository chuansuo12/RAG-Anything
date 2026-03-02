#!/usr/bin/env python
"""
读取 parquet 文件并显示前几行数据

用法示例:
  python eval/read_input.py runtime/eval/train-00000-of-00001.parquet
  python eval/read_input.py runtime/eval/train-00000-of-00001.parquet --n 10
"""

import argparse
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser(
        description="读取 parquet 文件并显示前几行数据",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "input_path",
        type=str,
        help="输入的 parquet 文件路径",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=5,
        help="显示前 N 行数据（默认 5 行）",
    )
    parser.add_argument(
        "--show_info",
        action="store_true",
        help="显示数据集基本信息（行数、列名、数据类型等）",
    )

    args = parser.parse_args()

    input_path = Path(args.input_path)
    if not input_path.exists():
        print(f"错误: 文件不存在: {input_path}")
        return

    print(f"正在读取: {input_path}")
    print("-" * 80)

    try:
        df = pd.read_parquet(input_path)

        # 显示基本信息
        if args.show_info:
            print(f"\n数据集基本信息:")
            print(f"  总行数: {len(df)}")
            print(f"  总列数: {len(df.columns)}")
            print(f"\n列名和数据类型:")
            for col in df.columns:
                dtype = df[col].dtype
                non_null = df[col].notna().sum()
                print(f"  - {col}: {dtype} (非空值: {non_null}/{len(df)})")
            print("-" * 80)

        # 显示前 N 行
        n = min(args.n, len(df))
        print(f"\n前 {n} 行数据:\n")
        print(df.head(n).to_string(index=True))
        print(f"\n(共 {len(df)} 行，显示前 {n} 行)")

    except Exception as e:
        print(f"读取文件时出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
