#!/usr/bin/env python
"""
按 doc_id 聚合统计行数，并输出前 N 个最多的 doc_id

用法示例:
  python eval/stats_by_docid.py runtime/eval/train-00000-of-00001.parquet
  python eval/stats_by_docid.py runtime/eval/train-00000-of-00001.parquet --top 10 --docid_col docid
"""

import argparse
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser(
        description="按 doc_id 聚合统计行数，倒序输出前 N 个",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "input_path",
        type=str,
        help="输入的 parquet 文件路径",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="输出前 N 个 doc_id（默认 10 个）",
    )
    parser.add_argument(
        "--docid_col",
        type=str,
        default="doc_id",
        help="doc_id 列名（默认 'docid'）",
    )
    parser.add_argument(
        "--show_all",
        action="store_true",
        help="显示所有 doc_id 的统计（不限制数量）",
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

        # 检查列是否存在
        if args.docid_col not in df.columns:
            print(f"错误: 列 '{args.docid_col}' 不存在")
            print(f"可用的列: {', '.join(df.columns)}")
            return

        # 按 doc_id 聚合统计
        print(f"\n按 '{args.docid_col}' 进行聚合统计...")
        stats = df[args.docid_col].value_counts().sort_values(ascending=False)

        # 显示总体信息
        total_rows = len(df)
        unique_docids = len(stats)
        print(f"\n总体统计:")
        print(f"  总行数: {total_rows}")
        print(f"  唯一 doc_id 数量: {unique_docids}")
        print(f"  平均每个 doc_id 行数: {total_rows / unique_docids:.2f}")
        print("-" * 80)

        # 显示前 N 个
        if args.show_all:
            top_stats = stats
            print(f"\n所有 doc_id 统计（共 {len(stats)} 个，按数量倒序）:\n")
        else:
            top_stats = stats.head(args.top)
            print(f"\n前 {args.top} 个 doc_id 统计（按数量倒序）:\n")

        # 格式化输出
        print(f"{'排名':<6} {'doc_id':<50} {'数量':<10} {'占比':<10}")
        print("-" * 80)

        for rank, (doc_id, count) in enumerate(top_stats.items(), 1):
            percentage = (count / total_rows) * 100
            # 如果 doc_id 太长，截断显示
            doc_id_str = str(doc_id)
            if len(doc_id_str) > 48:
                doc_id_str = doc_id_str[:45] + "..."
            print(f"{rank:<6} {doc_id_str:<50} {count:<10} {percentage:>6.2f}%")

        print("-" * 80)

        # 显示统计摘要
        if not args.show_all and len(stats) > args.top:
            remaining_count = stats.iloc[args.top:].sum()
            remaining_docids = len(stats) - args.top
            print(f"\n其他 {remaining_docids} 个 doc_id 共 {remaining_count} 行 "
                  f"({remaining_count / total_rows * 100:.2f}%)")

    except Exception as e:
        print(f"处理文件时出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
