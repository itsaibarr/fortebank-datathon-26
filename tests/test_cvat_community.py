"""Synthetic Compose fixture; no Docker runtime or competition content."""

import importlib.util
from pathlib import Path

import yaml


def test_local_review_proxy_has_host_access_while_annotation_backend_stays_internal(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "cvat_community", Path(__file__).parents[1] / "scripts/cvat_community.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = [
        "cvat_db",
        "cvat_redis_inmem",
        "cvat_redis_ondisk",
        "cvat_server",
        "cvat_worker_import",
        "cvat_worker_export",
        "cvat_worker_chunks",
        "cvat_ui",
        "cvat_opa",
    ]
    (tmp_path / "upstream-compose.yml").write_text(
        yaml.safe_dump(
            dict(
                services={
                    name: dict(image="synthetic/fixture:1", networks=["cvat"]) for name in names
                },
                volumes={},
            )
        )
    )
    module.prepare(tmp_path)
    config = yaml.safe_load((tmp_path / "compose.yml").read_bytes())
    proxy = config["services"]["proxy"]
    assert set(proxy["networks"]) == {"cvat", "review_access"}
    assert config["networks"]["cvat"]["internal"] is True
    assert config["networks"]["review_access"]["internal"] is False
    assert proxy["ports"] == ["127.0.0.1:18080:8080"]
    for name in names:
        assert config["services"][name]["networks"] == ["cvat"]
        assert not config["services"][name].get("ports")
