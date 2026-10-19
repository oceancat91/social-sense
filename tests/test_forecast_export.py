"""Numeric deployment exports preserve trained weights and evaluation metadata."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from social_forecast.scripts.export_numeric_checkpoint import (  # noqa: E402
    export_numeric_checkpoint,
    main,
)


@pytest.fixture
def checkpoint(tmp_path):
    payload = {
        "version": "social_forecast_ckpt_v1",
        "created_at": "2026-10-19T00:00:00+00:00",
        "domain": "SocialMedia_log",
        "capacity": "lite",
        "config": {"seq_len": 28, "pred_len": 6, "use_ds_saa": True},
        "scaler": {"mean": [1.25], "scale": [0.75]},
        "gate": {"silent_C": False, "theta": 0.6, "drop": ["T"]},
        "response_lib": {"K": 1, "templates": torch.tensor([[0.2, 0.3]])},
        "metrics": {"test_mse": 0.123, "direction_accuracy": 0.8},
        "extra": {"seed": 2025, "training": {"epochs": 15}},
        "custom_metadata": {"preserve": True},
        "model_state": {
            "delta_mlp.weight": torch.tensor([[1.0, 2.0]]),
            "delta_mlp_txt.weight": torch.tensor([[3.0, 4.0]]),
            "C_full": torch.tensor([[0.5], [0.0]]),
            "dssaa.semantic.encoder.weight": torch.ones(2, 2),
            "dssaa.blocks.T.weight": torch.ones(1, 2),
        },
        "dssaa_state": {"semantic.encoder.weight": torch.ones(2, 2)},
    }
    path = tmp_path / "full.pt"
    torch.save(payload, path)
    return path, payload


def test_export_preserves_weights_metadata_and_calibration(checkpoint, tmp_path):
    source, original = checkpoint
    calibration = b'{"spike_threshold": 0.477, "split": "train"}\n'
    source.with_name(source.name + ".spike_calib.json").write_bytes(calibration)
    output = tmp_path / "deployment" / "numeric.pt"

    assert export_numeric_checkpoint(source, output) == output.resolve()
    exported = torch.load(output, map_location="cpu", weights_only=False)

    assert set(exported) == set(original)
    for key in original.keys() - {"model_state", "dssaa_state", "response_lib"}:
        assert exported[key] == original[key]
    assert exported["response_lib"]["K"] == 1
    torch.testing.assert_close(
        exported["response_lib"]["templates"], original["response_lib"]["templates"]
    )
    assert exported["dssaa_state"] is None
    assert set(exported["model_state"]) == {
        "delta_mlp.weight", "delta_mlp_txt.weight", "C_full"
    }
    for name, tensor in exported["model_state"].items():
        torch.testing.assert_close(tensor, original["model_state"][name])
        assert tensor.device.type == "cpu"
    assert output.with_name(output.name + ".spike_calib.json").read_bytes() == calibration
    assert torch.load(source, weights_only=False)["dssaa_state"] is not None


def test_export_without_calibration_and_cli(checkpoint, tmp_path):
    source, _ = checkpoint
    output = tmp_path / "numeric.pt"

    main(["--checkpoint", str(source), "--output", str(output)])

    assert output.is_file()
    assert not output.with_name(output.name + ".spike_calib.json").exists()


def test_export_rejects_source_as_output(checkpoint):
    source, _ = checkpoint
    before = source.read_bytes()

    with pytest.raises(ValueError, match="different paths"):
        export_numeric_checkpoint(source, source.parent / "." / source.name)

    assert source.read_bytes() == before


@pytest.mark.parametrize("existing_sidecar", [False, True])
def test_export_rejects_existing_targets(checkpoint, tmp_path, existing_sidecar):
    source, _ = checkpoint
    output = tmp_path / "numeric.pt"
    existing = output.with_name(output.name + ".spike_calib.json") if existing_sidecar else output
    existing.write_bytes(b"existing artifact")

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        export_numeric_checkpoint(source, output)

    assert existing.read_bytes() == b"existing artifact"
    if existing_sidecar:
        assert not output.exists()


def test_export_supports_legacy_torch_serialization(checkpoint, tmp_path):
    source, original = checkpoint
    torch.save(original, source, _use_new_zipfile_serialization=False)
    output = tmp_path / "numeric.pt"

    export_numeric_checkpoint(source, output)

    assert torch.load(output, weights_only=False)["dssaa_state"] is None


def test_export_rejects_invalid_payload(tmp_path):
    source, output = tmp_path / "invalid.pt", tmp_path / "numeric.pt"
    torch.save({"model_state": [1, 2]}, source)

    with pytest.raises(ValueError, match="model_state mapping"):
        export_numeric_checkpoint(source, output)

    assert not output.exists()
