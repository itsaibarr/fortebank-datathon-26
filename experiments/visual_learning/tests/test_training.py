import numpy as np
import pytest

from forte_visual.training import admit, loss_labels, tiny_check


def test_measured_tokens_cannot_be_truncated_and_masks_exclude_inputs_images_padding(tmp_path):
    admit(7424, 768, 16)
    for args in [(7425, 768, 16), (100, 100, 17), (0, 1, 1)]:
        with pytest.raises(ValueError):
            admit(*args)
    labels = loss_labels(
        [1, 2, 99, 5, 6, 99, 0], 3, image_ids=[99], attention=[1, 1, 1, 1, 1, 1, 0]
    )
    assert labels.tolist() == [-100, -100, -100, 5, 6, -100, -100]
    with pytest.raises(ValueError):
        loss_labels([1, 2], 2)
    report = tiny_check(tmp_path / "train")
    assert report["finite"] and report["reload_max_abs_error"] == 0
    assert report["supervised_tokens"] == 3
    assert not report["establishes_full_model_fit"]
    assert np.isfinite(report["loss"])
