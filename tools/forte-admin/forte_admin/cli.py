"""Administrator entry point. Reviewers use the application browser address."""

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from forte_admin.client import ClientError
from forte_admin.config import ConfigError, apply, plan, read_json
from forte_admin.diagnostics import diagnose, run, safe_logs

DEFAULT_ROOT = str(Path.home() / ".local/share/forte-admin/installations/default")


def portable():
    path = Path(__file__).resolve().parents[3] / "deploy/portable/runtime.py"
    if not path.is_file():
        raise ConfigError(
            "Deployment resources missing; use the complete released archive or "
            "repository checkout."
        )
    spec = importlib.util.spec_from_file_location("forte_portable_runtime", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def output(value):
    print(json.dumps(value, indent=2, sort_keys=True))


def parser():
    p = argparse.ArgumentParser(
        prog="forte-admin",
        description="Install and operate Forte; reviewers use its browser application.",
    )
    p.add_argument("--version", action="version", version="forte-admin 0.2.0")
    sub = p.add_subparsers(dest="command", required=True)
    setup = sub.add_parser(
        "setup", help="Preview configuration; --apply writes state without starting services."
    )
    setup.add_argument("--installation", default=DEFAULT_ROOT)
    setup.add_argument(
        "--config", help="Nonsecret installation configuration JSON, never a connection profile"
    )
    setup.add_argument("--mode", choices=["private", "attach"])
    setup.add_argument("--manifest", dest="integration_manifest")
    setup.add_argument("--resources-root")
    setup.add_argument("--data-root")
    setup.add_argument("--secrets-root")
    setup.add_argument("--origin")
    setup.add_argument("--bind-address")
    setup.add_argument("--https-port", type=int)
    setup.add_argument("--bridge-port", type=int)
    setup.add_argument("--proxy-image")
    setup.add_argument("--attach-upstream")
    setup.add_argument("--tls-cert")
    setup.add_argument("--tls-key")
    setup.add_argument("--access-mode", choices=["browser-session", "gateway-single-admin"])
    setup.add_argument("--htpasswd-file")
    setup.add_argument("--gpu-index", type=int)
    setup.add_argument("--gpu-uuid")
    setup.add_argument("--session-port", type=int)
    setup.add_argument("--deployment-mode", choices=["private", "hosted"])
    setup.add_argument(
        "--preview", action="store_true", help="Explicit nonmutating preview (also the default)"
    )
    setup.add_argument("--apply", action="store_true")
    installer = sub.add_parser(
        "install", help="Guided, resumable preparation and startup in one invocation"
    )
    installer.add_argument("--installation", default=DEFAULT_ROOT)
    installer.add_argument(
        "--config", help="Nonsecret installation configuration JSON, never a connection profile"
    )
    installer.add_argument("--mode", choices=["private", "attach"])
    installer.add_argument("--manifest", dest="integration_manifest")
    installer.add_argument("--resources-root")
    installer.add_argument("--data-root")
    installer.add_argument("--secrets-root")
    installer.add_argument("--origin")
    installer.add_argument("--bind-address")
    installer.add_argument("--https-port", type=int)
    installer.add_argument("--bridge-port", type=int)
    installer.add_argument("--proxy-image")
    installer.add_argument("--attach-upstream")
    installer.add_argument("--tls-cert")
    installer.add_argument("--tls-key")
    installer.add_argument("--access-mode", choices=["browser-session", "gateway-single-admin"])
    installer.add_argument("--htpasswd-file")
    installer.add_argument(
        "--preview", action="store_true", help="Explicit nonmutating preview (also the default)"
    )
    installer.add_argument("--apply", action="store_true")
    installer.add_argument("--gpu-index", type=int)
    installer.add_argument("--gpu-uuid")
    installer.add_argument("--session-port", type=int)
    installer.add_argument("--deployment-mode", choices=["private", "hosted"])
    installer.add_argument(
        "--online",
        action="store_true",
        help="Allow only pinned public resource and image preparation",
    )
    installer.add_argument(
        "--resource-source",
        action="append",
        help="Prepared public resources directory; repeat for additional sources",
    )
    installer.add_argument("--image-artifact", help="Approved docker-save core image artifact")
    installer.add_argument(
        "--build-core",
        action="store_true",
        help="Explicitly build bundled pinned public source; does not approve runtime acceptance",
    )
    installer.add_argument(
        "--core-source", help="Released archive directory containing core-source and RELEASE.json"
    )
    installer.add_argument(
        "--node-image",
        default="node@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392",
        help="Immutable public Node builder image",
    )
    installer.add_argument(
        "--tls-mode", choices=["supplied", "local-self-signed"], default="supplied"
    )
    installer.add_argument(
        "--administrator", help="First browser account username; password prompted locally"
    )
    installer.add_argument(
        "--admin-password-file", help="Private password file for unattended first account bootstrap"
    )
    installer.add_argument("--readiness-timeout", type=float, default=360)
    installer.add_argument(
        "--qualification",
        action="store_true",
        help="Bounded local-only first model load; no browser/public activation",
    )
    for name in ("doctor", "up", "status", "logs", "stop", "prepare", "qualify"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--installation", default=DEFAULT_ROOT)
        cmd.add_argument(
            "--json", action="store_true", help="Output is always machine-readable JSON"
        )
        if name == "prepare":
            cmd.add_argument(
                "--images",
                action="store_true",
                required=True,
                help="Explicit online preparation: pull only pinned public images",
            )
    connect = sub.add_parser(
        "connect", help="Bind a separate API credential to an explicit processing endpoint"
    )
    connect.add_argument("--endpoint", required=True)
    connect.add_argument("--key-file", required=True)
    connect.add_argument(
        "--gateway-credentials-file",
        help="Optional private username:password file for a single-administrator gateway",
    )
    connect.add_argument("--profile", required=True)
    connect.add_argument("--api-version", type=int, choices=[1, 2], default=2)
    analyze = sub.add_parser(
        "analyze", help="Submit to a selected endpoint; this is hosted if the endpoint is remote"
    )
    analyze.add_argument("--profile", required=True)
    analyze.add_argument("--file", required=True)
    analyze.add_argument("--submit", action="store_true", required=True)
    analyze.add_argument("--wait", action="store_true")
    analyze.add_argument("--timeout", type=float, default=300)
    analyze.add_argument("--output", help="Optional full private result file outside Git")
    job = sub.add_parser("job")
    job.add_argument("--profile", required=True)
    job.add_argument("--job-id", required=True)
    job.add_argument("--output", help="Optional full private result file outside Git")
    return p


def client_command(args):
    from forte_admin.client import APIClient, load_profile, save_profile

    if args.command == "connect":
        profile = save_profile(
            Path(args.profile),
            args.endpoint,
            Path(args.key_file),
            args.api_version,
            gateway_credentials_file=args.gateway_credentials_file,
        )
        output(
            {
                "profile": str(Path(args.profile).resolve()),
                "processing_destination": profile["endpoint"],
                "api_version": profile["api_version"],
                "installation_created": False,
            }
        )
        return 0
    profile = load_profile(Path(args.profile))
    print("Processing destination: " + profile["endpoint"], file=sys.stderr)
    client = APIClient(
        profile["endpoint"],
        Path(profile["key_file"]),
        profile["api_version"],
        gateway_credentials_file=profile.get("gateway_credentials_file"),
    )
    if args.command == "analyze":
        result = client.upload(Path(args.file))
        if args.wait:
            result = client.wait(result["job_id"], timeout=args.timeout)
    else:
        result = client.job(args.job_id)
    if args.output:
        from forte_admin.config import installation_root, private_write

        path = installation_root(args.output)
        protected = {
            Path(args.profile).expanduser().resolve(),
            Path(profile["key_file"]).resolve(),
            Path(str(profile["key_file"]) + ".forte-origin.json").resolve(),
        }
        if path in protected or path.exists():
            raise ConfigError(
                "Result output must be a new private file, separate from connection credentials."
            )
        private_write(path, json.dumps(result, indent=2) + "\n")
    summary = {key: result[key] for key in ("job_id", "status") if key in result}
    summary["processing_destination"] = profile["endpoint"]
    summary["full_result_saved"] = bool(args.output)
    output(summary)
    return 5 if result.get("status") == "failed" else 0


def resolve_gpu(config, runtime=None, target=None):
    from forte_admin.hardware import inspect_host

    if runtime is not None and target is not None and runtime.owned_running(config, target):
        return {
            "can_attempt": True,
            "status": "owned_runtime_resume",
            "warnings": [
                "Resuming this installation's verified container identity; "
                "no second model is loaded."
            ],
        }

    manifest = (
        read_json(config["integration_manifest"]) if config.get("integration_manifest") else {}
    )
    report = inspect_host(config, manifest)
    if config["mode"] == "private" and report.get("can_attempt") and report.get("selected_gpu"):
        config["gpu_index"] = report["selected_gpu"]["index"]
        config["gpu_uuid"] = report["selected_gpu"]["uuid"]
    return report


def install_command(args, runtime, root):
    from forte_admin.install import install
    from forte_admin.preparation import bootstrap_administrator, prepare_application

    if args.preview and args.apply:
        raise ConfigError("Choose --preview or --apply.")
    changes = read_json(args.config) if args.config else {}
    for key in (
        "mode",
        "integration_manifest",
        "resources_root",
        "data_root",
        "secrets_root",
        "origin",
        "bind_address",
        "https_port",
        "bridge_port",
        "proxy_image",
        "attach_upstream",
        "tls_cert",
        "tls_key",
        "access_mode",
        "htpasswd_file",
        "gpu_index",
        "gpu_uuid",
        "session_port",
        "deployment_mode",
    ):
        value = getattr(args, key, None)
        if value is not None:
            changes[key] = value
    # Public release defaults are pinned; no fabricated remote image or inference endpoint.
    if not (root / "installation.json").exists() and not changes.get("integration_manifest"):
        candidate = (
            Path(__file__).resolve().parents[3] / "deploy/portable/core-current.candidate.json"
        )
        if candidate.is_file():
            changes["integration_manifest"] = str(candidate)
    config, _ = plan(root, changes)
    config["qualification_timeout"] = args.readiness_timeout
    report = install(
        config,
        root,
        apply=args.apply,
        runtime=runtime,
        prepare_resources=prepare_application,
        resource_options={
            "online": args.online,
            "source_dir": args.resource_source,
            "image_artifact": args.image_artifact,
            "config": config,
            "qualification": args.qualification,
            "build_core": args.build_core,
            "core_source": args.core_source,
            "node_image": args.node_image,
            "installation": root,
        },
        host_check=lambda selected: resolve_gpu(selected, runtime, root / "runtime"),
        bootstrap=lambda selected, installation, preview=False: bootstrap_administrator(
            selected,
            installation,
            username=args.administrator,
            password_file=args.admin_password_file,
            preview=preview,
        ),
        tls_mode=args.tls_mode,
        readiness_timeout=args.readiness_timeout,
        qualification=args.qualification,
        reporter=lambda event: print(event["phase"] + ": " + event["status"], file=sys.stderr),
    )
    output(report)
    return report.get("exit_code", 0 if report.get("ok") else 2)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command in {"connect", "analyze", "job"}:
            return client_command(args)
        runtime = portable()
        root = Path(args.installation).expanduser().resolve()
        if args.command == "install":
            return install_command(args, runtime, root)
        if args.command == "setup":
            if args.preview and args.apply:
                raise ConfigError("Choose --preview or --apply.")
            changes = read_json(args.config) if args.config else {}
            for key in (
                "mode",
                "integration_manifest",
                "resources_root",
                "data_root",
                "secrets_root",
                "origin",
                "bind_address",
                "https_port",
                "bridge_port",
                "proxy_image",
                "attach_upstream",
                "tls_cert",
                "tls_key",
                "access_mode",
                "htpasswd_file",
                "gpu_index",
                "gpu_uuid",
                "session_port",
                "deployment_mode",
            ):
                if getattr(args, key, None) is not None:
                    changes[key] = getattr(args, key)
            config, previous = plan(root, changes)
            # A connection profile cannot become installation configuration.
            if "endpoint" in changes or "key_file" in changes:
                raise ConfigError(
                    "Client connection profiles and installation configuration are separate."
                )
            immutable = ("mode", "project_name", "data_root", "secrets_root")
            if previous and any(previous.get(key) != config.get(key) for key in immutable):
                raise ConfigError(
                    "Changing installation ownership or storage requires a separate "
                    "installation and an explicit migration; existing state was preserved."
                )
            blockers = runtime.prerequisites(config)
            render = runtime.render if not runtime.validate(config) else lambda config, target: []
            files = apply(root, config, render) if args.apply else []
            output(
                {
                    "applied": args.apply,
                    "processing_destination": config["origin"],
                    "mode": config["mode"],
                    "configuration": config,
                    "unresolved_prerequisites": blockers,
                    "generated_files": [str(p) for p in files],
                    "services_started": False,
                    "administrator_bootstrap": (
                        "Provided by the core browser session layer; no administrator account "
                        "is fabricated."
                    ),
                }
            )
            return 0
        config = read_json(root / "installation.json")
        target = root / "runtime"
        if args.command == "doctor":
            report = diagnose(config, runtime.prerequisites)
            output(report)
            return 0 if report["ready_to_install"] else 2
        if args.command == "logs":
            output(safe_logs(config, target))
            return 0
        if args.command == "prepare":
            import re

            images = [config.get("proxy_image", "")]
            if config["mode"] == "private":
                images.append(config.get("core_image", ""))
            if not all(
                re.fullmatch(r"(?:[A-Za-z0-9./:_-]+@)?sha256:[0-9a-f]{64}", image)
                for image in images
            ):
                raise ConfigError(
                    "Preparation requires immutable image references from the verified "
                    "release manifest and proxy selection."
                )
            for image in images:
                if image.startswith("sha256:"):
                    code, _ = run(["docker", "image", "inspect", image])
                    if code:
                        raise ConfigError(
                            "The pinned local core image is missing. Import the approved "
                            "docker-save artifact with docker load; it cannot be pulled from a "
                            "registry."
                        )
                    continue
                try:
                    result = subprocess.run(
                        ["docker", "pull", image],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=1800,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise ConfigError(
                        "Image preparation incomplete; retry the same pinned image to resume. "
                        "No service was started."
                    ) from exc
                if result.returncode:
                    raise ConfigError(
                        "Image preparation failed; check public registry access locally and "
                        "retry. No service was started."
                    )
            output(
                {
                    "images_prepared": len(images),
                    "case_processing_started": False,
                    "resources": (
                        "Weights, tracking and official legal assets must be installed and "
                        "hash-verified from the selected release inventory; no external "
                        "inference fallback exists."
                    ),
                }
            )
            return 0
        if args.command in {"up", "qualify"}:
            resolve_gpu(config, runtime, target)
            from forte_admin.config import private_write

            private_write(root / "installation.json", json.dumps(config, indent=2) + "\n")
        result = runtime.lifecycle(config, target, args.command)
        output(result)
        if args.command == "up":
            return 0 if result.get("ok") and result.get("ready") else 2
        return 0 if result.get("ok", False) else 2
    except (ClientError, ConfigError, ValueError, OSError, RuntimeError) as exc:
        # Never render arbitrary exception values from subprocesses, HTTP or case files.
        if isinstance(exc, ClientError):
            output({"error": exc.as_dict()})
            return exc.exit_code
        message = (
            str(exc)
            if isinstance(exc, ConfigError)
            else (
                "Operation incomplete. Run doctor and inspect prerequisites locally; "
                "credentials and case content were withheld."
            )
        )
        output({"error": {"code": "configuration_error", "message": message}})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
