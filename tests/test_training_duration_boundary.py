import pytest

from research.diagnose_training_duration import load_split


def test_duration_diagnosis_rejects_test_split_before_any_file_access(tmp_path):
    with pytest.raises(ValueError, match="training/validation only"):
        load_split({}, "test", tmp_path)


def test_duration_diagnosis_checks_trace_identity_before_deserialization(tmp_path):
    pytest.importorskip("safetensors.torch")
    directory = tmp_path / ".cache/cost-quality-v1"
    directory.mkdir(parents=True)
    (directory / "trace-1024-11-4096.safetensors").write_bytes(b"not a safetensors file")
    study = {
        "config": {"splits": {"train": [11]}, "window_offsets": [4096]},
        "captures": [{"context": 1024, "book": 11, "offset": 4096, "trace_sha256": "0" * 64}],
    }
    with pytest.raises(ValueError, match="identity mismatch"):
        load_split(study, "train", tmp_path)
