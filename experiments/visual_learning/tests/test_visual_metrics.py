from forte_visual.evaluation import scan_metrics, track_metrics
from forte_visual.release import verify
from forte_visual.scan import scan
from forte_visual.synthetic import create


def test_tracking_metrics_use_reviewed_visible_geometry_and_count_fragmentation(tmp_path):
    release = create(tmp_path / "source")
    _, m, _ = verify(release)[1][0]
    automatic = m.model_copy(deep=True)
    same = track_metrics(m, automatic)
    assert same["geometry_recall"] == 1 and same["id_switches"] == 0
    automatic.segments[0].boxes.pop(5)
    fragmented = track_metrics(m, automatic)
    assert fragmented["fragments"] == 1 and fragmented["missing_boxes"] == 1


def test_proposal_recall_and_scan_coverage_are_separate_from_omission_or_precision(tmp_path):
    release = create(tmp_path / "source")
    clip, m, a = verify(release)[1][0]
    report = scan(m, release.parent / clip.media, tmp_path / "scan")
    metrics = scan_metrics(m, a, report)
    assert metrics["reviewed_events"] == 1
    assert metrics["proposal_recall"] == 1
    assert metrics["unresolved_fraction"] == 1
    assert metrics["false_events_per_minute"] is None
    assert metrics["events"]["0.5"]["recall"] == 0
