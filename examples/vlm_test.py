from __future__ import annotations

"""
Simple test script for the ImageVLMTool.

Usage (example):
    OPENAI_API_KEY=xxx python -m examples.vlm_test

This will:
- Call the configured VLM (e.g. Qwen-VL) once
- Use a fixed image path and prompt taken from your logs
- Print the raw text response or error message
"""

from agent.tools import ImageVLMTool


def main() -> None:
    # 1. Instantiate the VLM image tool (uses global vision_model_func config)
    tool = ImageVLMTool()

    # 2. Payload copied from your example
    payload = {
        "image_path": "/Users/tengyujia/ml_project_3/RAG-Anything/runtime/source/11258b1255cc40b1bfe27f49fdd760fa/parsed/watch_d/images/f2d5e6e900380bbf2554e7f955d218189b799327ba7804fa2592b5a4ba2cc1ca.jpg",
        "prompt": (
            "Analyze this image showing the Down button functionality table for HUAWEI WATCH D. "
            "Extract all specifications including: operation types (press once, press and hold), "
            "functions, remarks/limitations, and any visual details about the button's location "
            "or appearance. Provide complete technical details."
        ),
        # You can optionally add a system prompt here if needed:
        # "system_prompt": "You are an expert technical documentation analyzer."
    }

    # 3. Invoke the tool synchronously and print the result
    print("===== ImageVLMTool test start =====")
    try:
        result = tool.invoke(payload)
        print("===== ImageVLMTool test result =====")
        print(result)
    except Exception as exc:
        print("===== ImageVLMTool test error =====")
        print(repr(exc))


if __name__ == "__main__":
    main()

