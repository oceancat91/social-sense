"""Export trained numeric weights without the attached DS-SAA/GPT-2 tensors.

Run from the repository root, using a trusted local training checkpoint::

    python social_forecast/scripts/export_numeric_checkpoint.py \
        --checkpoint path/to/full.pt --output path/to/numeric.pt

The original checkpoint schema, numeric weights, and training metadata are
preserved. Loading this artifact with ``with_text=False`` needs no GPT-2 model.
"""

from __future__ import annotations

import argparse
import shutil
from collections.abc import Mapping
from pathlib import Path

import torch


def _load_trusted_checkpoint(path: Path):
    """Use mapped CPU storage, falling back only for older Torch/save formats."""
    options = {"map_location": "cpu", "mmap": True, "weights_only": False}
    while True:
        try:
            return torch.load(path, **options)
        except TypeError as exc:
            message = str(exc)
            unsupported = next(
                (name for name in ("mmap", "weights_only")
                 if name in options and f"'{name}'" in message
                 and "unexpected keyword" in message),
                None,
            )
            if unsupported is None:
                raise
            del options[unsupported]
        except RuntimeError as exc:
            if (options.get("mmap") and
                    "mmap can only be used with files saved with" in str(exc)):
                del options["mmap"]
            else:
                raise


def export_numeric_checkpoint(checkpoint: str | Path, output: str | Path) -> Path:
    """Write a new numeric inference artifact; never overwrite existing files."""
    checkpoint = Path(checkpoint).resolve()
    output = Path(output).resolve()
    if checkpoint == output:
        raise ValueError("Checkpoint and output must be different paths")
    if not checkpoint.is_file():
        raise FileNotFoundError(f"Checkpoint does not exist: {checkpoint}")

    source_calibration = checkpoint.with_name(checkpoint.name + ".spike_calib.json")
    output_calibration = output.with_name(output.name + ".spike_calib.json")
    for target in (output, output_calibration):
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"Refusing to overwrite existing output: {target}")

    payload = _load_trusted_checkpoint(checkpoint)
    if not isinstance(payload, dict) or not isinstance(payload.get("model_state"), Mapping):
        raise ValueError(f"Invalid checkpoint: expected a model_state mapping in {checkpoint}")
    numeric_payload = dict(payload)
    numeric_payload["model_state"] = {
        name: tensor for name, tensor in payload["model_state"].items()
        if not name.startswith("dssaa.")
    }
    numeric_payload["dssaa_state"] = None

    output.parent.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        with output.open("xb") as stream:
            created.append(output)
            torch.save(numeric_payload, stream)
        if source_calibration.is_file():
            with source_calibration.open("rb") as source:
                with output_calibration.open("xb") as destination:
                    created.append(output_calibration)
                    shutil.copyfileobj(source, destination)
    except BaseException:
        for target in reversed(created):
            target.unlink(missing_ok=True)
        raise
    return output


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True,
                        help="Trusted local trained checkpoint to read")
    parser.add_argument("--output", type=Path, required=True,
                        help="New numeric checkpoint path (must not exist)")
    args = parser.parse_args(argv)
    output = export_numeric_checkpoint(args.checkpoint, args.output)
    print(f"Numeric checkpoint exported: {output}")


if __name__ == "__main__":
    main()
