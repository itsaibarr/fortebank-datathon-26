import importlib.util
from pathlib import Path

import yaml


def test_private_cvat_setup_limits_ports_disables_egress_and_omits_hosted_features(tmp_path):
    module_path = Path(__file__).resolve().parents[1] / "scripts/cvat_community.py"
    spec = importlib.util.spec_from_file_location("cvat_setup", module_path)
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
    services = {
        name: {
            "image": "synthetic",
            "container_name": "unscoped",
            "networks": ["cvat"],
            "depends_on": ["cvat_db"],
        }
        for name in names
    }
    services["cvat_db"].pop("depends_on")
    (tmp_path / "upstream-compose.yml").write_text(
        yaml.safe_dump({"services": services, "volumes": {}})
    )
    module.prepare(tmp_path)
    result = yaml.safe_load((tmp_path / "compose.yml").read_text())
    assert result["networks"]["cvat"]["internal"]
    assert result["services"]["proxy"]["ports"] == ["127.0.0.1:18080:8080"]
    assert all("container_name" not in s for s in result["services"].values())
    assert result["services"]["cvat_server"]["environment"]["CVAT_ANALYTICS"] == "0"
    assert "@sha256:" in result["services"]["cvat_server"]["image"]
    assert set(result["services"]) == set(names) | {"proxy"}
