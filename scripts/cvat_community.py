#!/usr/bin/env python3
"""Prepare/start an isolated local Community pilot from pinned upstream Compose.

Run using the private tracking environment (PyYAML). No private data is fetched
or uploaded by this setup script. Network egress is disabled on the CVAT network.
"""

import argparse
import hashlib
import json
import secrets
import subprocess
import urllib.request
from pathlib import Path

import yaml

CVAT_REVISION = "9176834830e2e931a8d3a6857dcf43c6cc0ee927"
SERVER = "cvat/server@sha256:4ed4d6bca5c023cfe1ade131625c0008d52bc0a8e6a940cb76b0213b156bde1e"
UI = "cvat/ui@sha256:d7f5132a2d2160465619e59c62a02a0ec4b5b856314cdbd1fbb22066b7d09939"
PROJECT = "forte26-cvat-v1"


def docker(directory, *args, **kwargs):
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "-f", str(directory / "compose.yml"), *args],
        check=True,
        **kwargs,
    )


def prepare(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    upstream = directory / "upstream-compose.yml"
    if not upstream.exists():
        url = f"https://raw.githubusercontent.com/cvat-ai/cvat/{CVAT_REVISION}/docker-compose.yml"
        with urllib.request.urlopen(url, timeout=30) as response:
            upstream.write_bytes(response.read())
    original = yaml.safe_load(upstream.read_bytes())
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
    services = {key: original["services"][key] for key in names}
    for name, service in services.items():
        service.pop("container_name", None)
        service.pop("labels", None)
        service["restart"] = "unless-stopped"
        if "depends_on" in service:
            deps = service["depends_on"]
            service["depends_on"] = (
                {key: value for key, value in deps.items() if key in names}
                if isinstance(deps, dict)
                else [key for key in deps if key in names]
            )
        env = service.setdefault("environment", {})
        if name.startswith("cvat_worker") or name == "cvat_server":
            env.update(CVAT_ANALYTICS="0", DJANGO_LOG_SERVER_HOST="", NUMPROCS="1")
            env.update(
                ALLOWED_HOSTS="localhost,127.0.0.1,cvat-server",
                CVAT_BASE_URL="http://localhost:18080",
            )
        if name == "cvat_server" or name.startswith("cvat_worker"):
            service["image"] = SERVER
            service["platform"] = "linux/amd64"
        elif name == "cvat_ui":
            service["image"] = UI
            service["platform"] = "linux/amd64"
    services["proxy"] = dict(
        image="nginx:1.29-alpine",
        restart="unless-stopped",
        ports=["127.0.0.1:18080:8080"],
        # Docker does not publish this port from an internal-only network.
        # Only the loopback proxy gets a host-access network; data services
        # remain exclusively on the internal backend network.
        networks=["cvat", "review_access"],
        depends_on=["cvat_server", "cvat_ui"],
        volumes=[str((directory / "proxy.conf").resolve()) + ":/etc/nginx/conf.d/default.conf:ro"],
    )
    (directory / "proxy.conf").write_text("""server {
 listen 8080; server_name localhost; client_max_body_size 256m;
 proxy_read_timeout 300s; proxy_connect_timeout 15s;
 location ~ ^/(api|static|admin|django-rq)/ {
   proxy_pass http://cvat_server:8080;
   proxy_set_header Host $http_host;
   proxy_set_header X-Forwarded-Proto $scheme;
   proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
 }
 location / { proxy_pass http://cvat_ui:8000; proxy_set_header Host $http_host; }
}
""")
    volume_names = set()
    for service in services.values():
        for item in service.get("volumes", []):
            if isinstance(item, str) and item.split(":")[0] in original.get("volumes", {}):
                volume_names.add(item.split(":")[0])
    result = dict(
        name=PROJECT,
        services=services,
        networks={"cvat": {"internal": True}, "review_access": {"internal": False}},
        volumes={name: {} for name in volume_names},
    )
    (directory / "compose.yml").write_text(yaml.safe_dump(result, sort_keys=False))
    (directory / "upstream-receipt.json").write_text(
        json.dumps(
            dict(
                cvat_revision=CVAT_REVISION,
                upstream_sha256=hashlib.sha256(upstream.read_bytes()).hexdigest(),
                server_image=SERVER,
                ui_image=UI,
                loopback_only=True,
                network_internal=True,
                host_access_service="proxy",
                backend_egress_disabled=True,
                excluded=["analytics", "grafana", "webhooks", "cloud storage", "integrated SAM2"],
            ),
            indent=2,
        )
        + "\n"
    )
    credentials = directory / "local-credentials.json"
    if not credentials.exists():
        credentials.write_text(
            json.dumps(dict(username="forte26-local", password=secrets.token_urlsafe(24)))
        )
        credentials.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["prepare", "pull", "start", "stop", "status", "create-user"]
    )
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if any((parent / ".git").exists() for parent in [directory, *directory.parents]):
        raise ValueError("CVAT state must be outside Git")
    if args.action == "prepare":
        prepare(directory)
    elif args.action == "pull":
        docker(directory, "pull")
    elif args.action == "start":
        docker(directory, "up", "-d")
    elif args.action == "stop":
        # Retain this project's persistent review volumes. No global pruning.
        docker(directory, "down")
    elif args.action == "status":
        docker(directory, "ps")
    else:
        credentials = json.loads((directory / "local-credentials.json").read_text())
        script = (
            "from django.contrib.auth import get_user_model\n"
            f"u,created=get_user_model().objects.get_or_create(username={credentials['username']!r})\n"
            f"u.set_password({credentials['password']!r})\n"
            "u.is_staff=True\nu.is_superuser=True\nu.save()\n"
        )
        docker(
            directory,
            "exec",
            "-T",
            "cvat_server",
            "python",
            "manage.py",
            "shell",
            input=script,
            text=True,
            capture_output=True,
        )
        print(
            json.dumps(
                dict(
                    local_user_ready=True,
                    url="http://localhost:18080",
                    credentials_file=str(directory / "local-credentials.json"),
                )
            )
        )


if __name__ == "__main__":
    main()
