"""Run the existing full lite experiment reproducibly, without replacing old runs.

Example (from the repository root)::

    .venv/Scripts/python.exe social_forecast/scripts/retrain_cpu.py \
        --run-id retrain_20261019 --encoder-dir path/to/gpt2

This trains the numeric, text, and joint stages. It is not a smoke checkpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from functools import partial
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class _Tee:
    def __init__(self, console, log):
        self.console, self.log = console, log

    def write(self, value):
        self.console.write(value)
        return self.log.write(value)

    def flush(self):
        self.console.flush()
        self.log.flush()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--encoder-dir", required=True, type=Path)
    parser.add_argument("--encoder-revision", default="")
    parser.add_argument("--seed", default=2025, type=int)
    parser.add_argument("--threads", default=2, type=int)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.run_id):
        parser.error("run-id must contain only letters, numbers, '_' or '-'")
    if args.threads < 1:
        parser.error("threads must be positive")
    encoder_dir = args.encoder_dir.resolve()
    if not (encoder_dir / "config.json").is_file():
        parser.error(f"missing local encoder config: {encoder_dir}")

    result_dir = ROOT / "results" / args.run_id
    checkpoint_dir = ROOT / "checkpoints" / args.run_id
    if result_dir.exists() or checkpoint_dir.exists():
        parser.error("run directory already exists; choose a new run-id")
    result_dir.mkdir(parents=True)
    checkpoint_dir.mkdir(parents=True)

    # Set CPU controls before importing torch; never read API keys or .env here.
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    os.environ["OMP_NUM_THREADS"] = str(args.threads)
    os.environ["MKL_NUM_THREADS"] = str(args.threads)
    os.environ["TEXT_CACHE_BS"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    import torch

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)

    data_path = ROOT / "data" / "SocialMedia_log.csv"
    source_path = ROOT / "test" / "test_event_response_e2e.py"
    training_args = [
        str(source_path), "SocialMedia_log", "--capacity", "lite",
        "--seq_len", "28", "--pred_len", "6", "--seasonal_period", "7",
        "--calendar", "short", "--no_ctx", "--direction", "--seed", str(args.seed),
        "--out", str(result_dir / "metrics.csv"), "--ckpt_dir", str(checkpoint_dir),
    ]
    manifest = {
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "torch": torch.__version__,
        "device": "cpu",
        "threads": args.threads,
        "seed": args.seed,
        "encoder_dir": str(encoder_dir),
        "encoder_revision": args.encoder_revision,
        "data_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "training_source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "training_argv": training_args,
        "checkpoint_dir": str(checkpoint_dir),
        "results_dir": str(result_dir),
    }
    manifest_path = result_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("forecast_retrain_entry", source_path)
    entry = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    try:
        spec.loader.exec_module(entry)
        entry.load_gpt2_encoder = partial(entry.load_gpt2_encoder, model_path=str(encoder_dir))
        sys.argv = training_args
        with (result_dir / "training.log").open("w", encoding="utf-8", buffering=1) as log:
            with redirect_stdout(_Tee(sys.stdout, log)):
                entry.main()
        checkpoint = checkpoint_dir / "SocialMedia_log_lite_pl6_L28.pt"
        if not checkpoint.is_file() or not checkpoint.with_suffix(".meta.json").is_file():
            raise RuntimeError("training finished without exporting a valid checkpoint and metadata")
        manifest["status"] = "trained"
        manifest["checkpoint"] = str(checkpoint)
        manifest["checkpoint_bytes"] = checkpoint.stat().st_size
    except BaseException as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
