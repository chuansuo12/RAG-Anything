#!/usr/bin/env python
"""
从 MinerU 已解析目录跑通 Demo：加载 content_list 后插入 RAG，并做 QA。

使用场景：你已经用 MinerU 解析好 PDF，结果在某个目录（如 paresed-documents/efd88e41...），
无需再解析，只需：
1. 配置 .env（API Key 等）
2. 运行本脚本指定该目录
3. 进行问答

用法示例:
  cd /Users/tengyujia/ml_project_3/RAG-Anything
  python examples/run_qa_from_parsed_dir.py \\
    /Users/tengyujia/ml_data/MMLongBench-Doc/paresed-documents/efd88e41c5f2606c57929cac6c1c0605

  指定工作目录:
  python examples/run_qa_from_parsed_dir.py /path/to/parsed_dir --working_dir ./my_rag_storage
"""

import os
import argparse
import asyncio
import logging
import logging.config
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

# load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=False)

from lightrag.utils import logger, set_verbose_debug
from raganything import RAGAnything, RAGAnythingConfig
from raganything.parser import MineruParser
from llm import llm_model_func, vision_model_func, embedding_func

# 默认日志
LOG_DIR = os.getenv("LOG_DIR", os.getcwd())
LOG_FILE = os.path.abspath(os.path.join(LOG_DIR, "run_qa_from_parsed_dir.log"))
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger.setLevel(logging.INFO)
set_verbose_debug(os.getenv("VERBOSE", "false").lower() == "true")


def load_content_list_from_parsed_dir(parsed_dir: Path):
    """
    从 MinerU 解析目录加载 content_list（与 MineruParser._read_output_files 约定一致）。
    目录内需包含 *_{content_list}.json，图片路径会被转为基于该目录的绝对路径。
    """
    parsed_dir = Path(parsed_dir).resolve()
    if not parsed_dir.is_dir():
        raise FileNotFoundError(f"解析目录不存在: {parsed_dir}")

    # 查找 *_content_list.json（与 MineruParser._read_output_files 约定一致）
    candidates = list(parsed_dir.glob("*_content_list.json"))
    if not candidates:
        raise FileNotFoundError(
            f"在 {parsed_dir} 下未找到 *_content_list.json，请确认是 MinerU 解析输出目录"
        )

    json_path = candidates[0]
    file_stem = json_path.stem.replace("_content_list", "")

    content_list, _ = MineruParser._read_output_files(
        parsed_dir, file_stem, method="auto"
    )
    if not content_list:
        raise ValueError(f"content_list 为空: {json_path}")
    return content_list, str(parsed_dir)


async def run_qa(
    parsed_dir: str,
    working_dir: str = "./rag_storage",
    query: str = None,
):
    content_list, file_path_ref = load_content_list_from_parsed_dir(Path(parsed_dir))
    logger.info(f"已从目录加载 {len(content_list)} 个内容块，引用路径: {file_path_ref}")

    config = RAGAnythingConfig(
        working_dir=working_dir,
        parser="mineru",
        parse_method="auto",
        enable_image_processing=True,
        enable_table_processing=True,
        enable_equation_processing=True,
        display_content_stats=True,
    )

    rag = RAGAnything(
        config=config,
        llm_model_func=llm_model_func,
        vision_model_func=vision_model_func,
        embedding_func=embedding_func,
    )

    logger.info("正在将 content_list 插入 RAG...")
    await rag.insert_content_list(
        content_list=content_list,
        file_path=file_path_ref,
        display_stats=True,
    )
    logger.info("插入完成，可进行问答。")

    if query:
        logger.info(f"提问: {query}")
        result = await rag.aquery(query, mode="hybrid")
        logger.info(f"回答: {result}")
        return result

    # 简单交互式问答
    print("\n输入问题回车进行 QA，输入 q 或 exit 退出。\n")
    while True:
        try:
            line = input(">>> ").strip()
        except EOFError:
            break
        if not line or line.lower() in ("q", "exit", "quit"):
            break
        result = await rag.aquery(line, mode="hybrid")
        print(result, "\n")


def main():
    parser = argparse.ArgumentParser(
        description="从 MinerU 已解析目录加载并跑通 RAG Demo QA",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "parsed_dir",
        type=str,
        help="MinerU 解析结果目录（内含 *_content_list.json 与 images/）",
    )
    parser.add_argument(
        "--working_dir", "-w",
        default=os.getenv("RAG_WORKING_DIR", "./rag_storage"),
        help="RAG 工作目录（LightRAG 存储）",
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        default=None,
        help="执行单次问答后退出；不传则进入交互式 QA",
    )
    args = parser.parse_args()
    asyncio.run(
        run_qa(
            parsed_dir=args.parsed_dir,
            working_dir=args.working_dir,
            query=args.query,
        )
    )


if __name__ == "__main__":
    main()
