"""Run every required command on public synthetic blocks, with zero paid resources."""

import argparse
import subprocess
import sys
from pathlib import Path

from forte_visual.io import private_dir, read, write


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    root = private_dir(args.output.resolve())

    def run(*arguments):
        subprocess.run([sys.executable, "-m", "forte_visual.cli", *map(str, arguments)], check=True)

    run("synthetic", "--output", root / "fixture")
    release = root / "snapshot/release.json"
    run("release-check", "--release", root / "fixture/release.json", "--snapshot", release.parent)
    run("export", "--release", release, "--output", root / "export")
    inputs, refs = root / "export/inference/inputs.json", root / "export/reference/answers.json"
    run(
        "compare",
        "--release",
        release,
        "--inputs",
        inputs,
        "--references",
        refs,
        "--mock",
        "--output",
        root / "comparison",
    )
    run(
        "evaluate",
        "--inputs",
        inputs,
        "--references",
        refs,
        "--predictions",
        root / "comparison/8b/predictions.json",
        "--output",
        root / "evaluation.json",
    )
    run("train", "--synthetic-check", "--output", root / "tiny-training")
    run("scan", "--release", release, "--clip", "clip000", "--mock", "--output", root / "scan")
    run(
        "evaluate-scan",
        "--release",
        release,
        "--timeline",
        root / "scan/timeline.json",
        "--output",
        root / "scan-metrics.json",
    )
    run(
        "evaluate-tracks",
        "--oracle",
        release.parent / "clip000/tracks.json",
        "--automatic",
        release.parent / "clip000/tracks.json",
        "--output",
        root / "track-metrics.json",
    )
    run(
        "compare",
        "--release",
        release,
        "--inputs",
        inputs,
        "--dry-run",
        "--output",
        root / "dry-compare",
    )
    run(
        "train",
        "--release",
        release,
        "--inputs",
        inputs,
        "--dry-run",
        "--output",
        root / "dry-train",
    )
    compared = read(root / "comparison/comparison.json")
    trained = read(root / "tiny-training/training-check.json")
    summary = {
        "synthetic_only": True,
        "model_weights_loaded": False,
        "paid_spend_usd": 0,
        "comparison_outcome": compared["outcome"],
        "groups": len(compared["scores"]["8b"]["groups"]),
        "metrics": compared["scores"]["8b"]["aggregate"],
        "scan": read(root / "scan-metrics.json"),
        "adapter_reload_error": trained["reload_max_abs_error"],
        "claim": "software mechanics only; no real actor/action accuracy or memory-fit evidence",
    }
    write(root / "aggregate.json", summary)
    print("Synthetic command workflow completed; aggregate.json contains scoped measurements")


if __name__ == "__main__":
    main()
