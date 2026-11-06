"""Run the evidence workbench with prompt B and an isolated demonstration DB."""
import argparse
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.main import create_app  # noqa: E402
from scripts.evaluate_model_ab import PROMPTS  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/model-demo.db")
    parser.add_argument("--port", type=int, default=8146)
    parser.add_argument("--model", default="qwen3:4b-instruct")
    parser.add_argument("--url", default="http://127.0.0.1:11435")
    args = parser.parse_args()
    app = create_app(args.db, {"model": args.model, "ollama_url": args.url,
        "system_prompt": PROMPTS["B"],
        "model_options": {"temperature": 0, "seed": 42, "num_ctx": 16384, "num_predict": 1024}})
    uvicorn.run(app, host="127.0.0.1", port=args.port)
