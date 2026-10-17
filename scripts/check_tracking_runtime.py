"""Synthetic offline integration check against the pinned actual ByteTrack package."""

import importlib.metadata
import json

from forte.person_proposals import LocalByteTrack
from forte.tracking import SegmentBuilder

tracker = LocalByteTrack(0.2)
guard = SegmentBuilder(0.2)
ids = []
for i in range(12):
    detections = [] if i == 8 else [((0.1 + 0.005 * i, 0.1, 0.3 + 0.005 * i, 0.9), 0.9)]
    tracked = tracker.update(detections, i * 0.2)
    guard.update(f"f{i:06d}", i * 0.2, tracked)
    if 0 < i < 8:
        ids.append(tracked[0][0])
assert len(set(ids)) == 1, "Pinned ByteTrack did not preserve continuous synthetic identity"
assert len(guard.segments) == 3  # initial unassociated box, activated track, post-gap segment
assert guard.segments[0].person_id != guard.segments[1].person_id
assert guard.joins and all(j.review.status == "draft" for j in guard.joins)
print(
    json.dumps(
        dict(
            synthetic_runtime_check=True,
            continuous_ids_preserved_after_activation=True,
            occlusion_join_unapproved=True,
            trackers=importlib.metadata.version("trackers"),
            onnxruntime=importlib.metadata.version("onnxruntime"),
        )
    )
)
