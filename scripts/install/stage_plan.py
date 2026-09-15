"""Pure planning for pinned container, runtime and acquisition inputs."""
from .acquisition import selected_manifests
from .runtime import runtime_plan
from .core import InstallError


def bounded_plan(config, repo, lock):
    if config["role"] == "client":
        return {}
    groups = {}
    unique = set()
    for group in ("docker", "toolkit"):
        names = lock["groups"][group]
        unique.update(names)
        groups[group] = {"requested": lock["requested"][group], "dependency_count": len(names),
                         "download_bytes": sum(lock["packages"][name]["size_bytes"] for name in names),
                         "root_installed_bytes": sum(lock["packages"][name]["installed_bytes"] for name in names)}
    selected = selected_manifests(config, repo, lock)
    runtimes = runtime_plan(config, repo, lock)
    blobs = {}
    for runtime in runtimes:
        for item in runtime["compressed_blob_descriptors"]:
            if item["digest"] in blobs and blobs[item["digest"]] != item["size_bytes"]:
                raise InstallError("runtime_registry_descriptor_size_conflict")
            blobs[item["digest"]] = item["size_bytes"]
    return {"container": {"groups": groups,
                "unique_dependency_download_bytes": sum(lock["packages"][name]["size_bytes"] for name in unique),
                "repositories": lock["container_repositories"], "gpu_gate": lock["gpu_container_gate"],
                "effects": ["install exact package closure using verified keys and private snapshot sources",
                    "suppress package service autostart and restore prior policy/masks",
                    "merge compatible Docker/containerd config; reject conflicting roots or live containers",
                    "prepare registered daemon/cache roots before explicit daemon start",
                    "start/restart Docker and containerd only with data mount ordering and verified roots",
                    "execute disposable pinned GPU container; no model activation"]},
            "runtimes": runtimes, "unique_runtime_blob_transfer_bytes": sum(blobs.values()),
            "acquisition": {"workers_total": 4, "max_attempts_per_artifact": 6,
                "selected": [{"selection": row["selection"], "manifest_sha256": row["sha256"],
                    "repo_id": row["manifest"]["repo_id"], "revision": row["manifest"]["revision"],
                    "destination": config["model_dir"] + "/" + row["directory"],
                    "artifact_count": row["manifest"]["artifact_count"], "bytes": row["manifest"]["total_bytes"]}
                    for row in selected],
                "effects": ["retain/resume verified-identity partial files on registered model storage",
                    "compute every expected SHA256 before promotion and completion",
                    "preserve rejected partials; next resume retries only missing artifacts",
                    "no model load or inference readiness claim"]}}
