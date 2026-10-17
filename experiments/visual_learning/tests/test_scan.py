import pytest
from forte.video import make_windows

from forte_visual.release import verify
from forte_visual.scan import Bounds, MockScanExecutor, RoleCache, assemble, fine_windows, scan
from forte_visual.synthetic import create


@pytest.mark.parametrize("duration", [0.1, 4, 16, 16.1, 145, 180])
def test_schedule_includes_both_endpoints_and_fine_images_are_three_calls(duration):
    windows = make_windows(duration, 16, 12)
    assert windows[0][0] == 0 and windows[-1][1] == duration
    assert all(b[0] <= a[1] for a, b in zip(windows, windows[1:], strict=False))
    assert fine_windows(10, 30) == [(6, 10), (8, 12), (10, 14)]


def fact(actor="p1", start=0, end=4, **updates):
    return {
        "actor_id": actor,
        "clip_id": "clip000",
        "segments": [actor],
        "other_actor_id": "p2",
        "kind": "action",
        "value": "exchange",
        "visibility": "observed",
        "start_sec": start,
        "end_sec": end,
        "start_frame_id": f"f{start}",
        "end_frame_id": f"f{end}",
        "continues_before_window": start > 0,
        "continues_after_window": True,
        "evidence_frame_ids": [f"f{start}"],
        **updates,
    }


def test_merge_preserves_actor_counterpart_gaps_and_clipped_outer_boundary():
    result = assemble([fact(), fact(start=2, end=6), fact(actor="p3"), fact(start=8, end=10)])
    assert len(result) == 3
    assert result[0]["start_sec"] == 0 and result[0]["end_sec"] == 6
    assert not result[0]["continues_before_window"] and result[0]["continues_after_window"]
    assert len(assemble([fact(), fact(other_actor_id="p4")])) == 2


def test_role_cache_never_promotes_agreement_or_inherits_unknown_segment():
    roles = RoleCache()
    roles.add("clip000", ["s1"], {"value": "cashier", "start_sec": 0, "end_sec": 6})
    roles.add("clip000", ["s1"], {"value": "cashier", "start_sec": 4, "end_sec": 8})
    assert roles.values[("clip000", ("s1",))]["review_status"] == "unreviewed"
    assert ("clip000", ("s2",)) not in roles.values
    roles.add("clip000", ["s1"], {"value": "customer"})
    assert roles.values[("clip000", ("s1",))]["value"] == "unclear"
    assert roles.conflicts


def test_mock_complete_scan_and_exhaustion_preserve_uncertainty(tmp_path):
    path = create(tmp_path / "release")
    clip, m, _ = verify(path)[1][0]
    result = scan(m, path.parent / clip.media, tmp_path / "scan")
    assert result["coverage"]["scheduled_coarse"] == [[0, 8]]
    assert result["coverage"]["sampled_frame_ids"][-1] == "f000015"
    assert not result["coverage"]["adequate_for_omission"]
    assert result["coverage"]["unresolved_ranges"] == [[0, 8]]
    assert result["visual_timeline"] == []
    exhausted = scan(m, path.parent / clip.media, tmp_path / "expired", bounds=Bounds(deadline=0))
    assert exhausted["status"] == "incomplete_budget"
    assert exhausted["calls"] == 0
    bounded = scan(
        m,
        path.parent / clip.media,
        tmp_path / "bounded",
        bounds=Bounds(deadline=10**12, max_calls=1),
    )
    assert bounded["status"] == "incomplete_budget"
    assert bounded["coverage"]["sampled_frame_ids"]


def test_mock_failure_is_incomplete_and_proposals_still_recorded(tmp_path):
    path = create(tmp_path / "release")
    clip, m, _ = verify(path)[1][0]

    class Broken(MockScanExecutor):
        def __call__(self, request, root, timeout):
            raise RuntimeError("Synthetic failure")

    result = scan(m, path.parent / clip.media, tmp_path / "scan", Broken())
    assert result["status"] == "incomplete_failures" and result["failures"]
    assert result["coverage"]["unresolved_ranges"]


def test_deadline_and_memory_overrun_do_not_become_complete_observations():
    clock = [0.0]
    budget = Bounds(deadline=5, clock=lambda: clock[0])

    def late(request, root, timeout):
        clock[0] = 6
        return {"facts": [], "input_tokens": 10, "output_tokens": 10}

    with pytest.raises(TimeoutError):
        budget.invoke(late, None, None)
    budget = Bounds(deadline=10, max_memory_bytes=10, clock=lambda: 0)
    with pytest.raises(TimeoutError):
        budget.invoke(lambda *a: {"peak_memory_bytes": 11}, None, None)


def test_complete_long_clip_scan_keeps_ids_and_last_source_frame(tmp_path):
    path = create(tmp_path / "release", count=1, duration=30)
    clip, m, _ = verify(path)[1][0]

    class Recording(MockScanExecutor):
        def __init__(self):
            self.requests = []

        def __call__(self, request, root, timeout):
            self.requests.append(request)
            return super().__call__(request, root, timeout)

    executor = Recording()
    result = scan(m, path.parent / clip.media, tmp_path / "scan", executor)
    assert result["status"] == "complete_schedule"
    assert result["coverage"]["scheduled_coarse"] == [[0, 16], [12, 28], [24, 30]]
    assert "f000059" in result["coverage"]["sampled_frame_ids"]
    assert all(c.actors == executor.requests[0].actors for c in executor.requests)
    assert all(
        len(c.views) == 16 and len(c.frames) == 8 for c in executor.requests if c.task == "action"
    )
    assert result["coverage"]["unresolved_ranges"] == [[0, 30]]
