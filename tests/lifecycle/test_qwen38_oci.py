"""Synthetic Docker inspect contracts; no container/image/VM operation."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from runtime import qwen38_oci as q


def inspected(domain="oci_config"):
    result = {"Id": q.CONFIG_DIGEST if domain == "oci_config" else q.MANIFEST_DIGEST,
              "RepoDigests": [q.IMAGE_REFERENCE], "Os": "linux", "Architecture": "amd64",
              "Config": {"Entrypoint": list(q.IMAGE_ENTRYPOINT), "Cmd": None,
                         "WorkingDir": q.IMAGE_WORKDIR,
                         "Labels": {"org.opencontainers.image.revision": q.SOURCE_REVISION,
                                    "org.opencontainers.image.source": q.SOURCE_REPOSITORY}}}
    if domain != "oci_config":
        result["Descriptor"] = {"digest": q.MANIFEST_DIGEST, "mediaType": q.MANIFEST_MEDIA_TYPE,
                                "size": q.MANIFEST_BYTES}
    return result


class OCIContract(unittest.TestCase):
    def test_both_reviewed_store_domains_produce_explicit_distinct_evidence(self):
        observed = [q.verify_image(inspected(domain))
                    for domain in ("oci_config", "oci_platform_manifest")]
        self.assertNotEqual(observed[0]["image_id"], observed[1]["image_id"])
        for e in observed:
            self.assertEqual(q.validate_evidence(e), e)
            self.assertEqual(e["config_digest"], q.CONFIG_DIGEST)
            self.assertEqual(e["platform_manifest_digest"], q.MANIFEST_DIGEST)
            c = {"Image": e["image_id"], "Config": {"Image": q.IMAGE_REFERENCE}}
            q.validate_container_image(c, e)

    def test_profile_and_reviewed_provenance_keep_config_identity_distinct(self):
        profile = json.loads((ROOT / "configs/runtimes/sglang-qwen38-0.5.19.json").read_text())
        source = json.loads((ROOT / "reports/q38s-provenance.json").read_text())["runtime"]
        self.assertEqual(profile["image_id"], q.CONFIG_DIGEST)
        self.assertEqual(profile["image_manifest_digest"], q.MANIFEST_DIGEST)
        self.assertEqual(profile["image_ref"], q.IMAGE_REFERENCE)
        self.assertEqual(source["manifest"]["digest"], q.MANIFEST_DIGEST)
        self.assertEqual(source["manifest"]["size_bytes"], q.MANIFEST_BYTES)
        self.assertEqual(source["config"]["digest"], q.CONFIG_DIGEST)
        self.assertEqual(source["config"]["size_bytes"], q.CONFIG_BYTES)
        self.assertEqual(source["image_default_entrypoint"], list(q.IMAGE_ENTRYPOINT))
        self.assertEqual(profile["entrypoint"], ["python3"])

    def test_unknown_id_tag_only_index_wrong_repo_and_platform_are_rejected(self):
        changes = [
            ("Id", "sha256:" + "a" * 64), ("Id", "lmsysorg/sglang:v0.5.19-cu130"),
            ("RepoDigests", []), ("RepoDigests", ["other/sglang@" + q.MANIFEST_DIGEST]),
            ("RepoDigests", [q.IMAGE_REFERENCE] * 2), ("RepoDigests", q.IMAGE_REFERENCE),
            ("RepoDigests", [{}]), ("Architecture", "arm64"), ("Os", "windows")]
        for name, value in changes:
            with self.subTest(name=name, value=value):
                row = inspected(); row[name] = value
                with self.assertRaises(q.Qwen38OCIError):
                    q.verify_image(row)

    def test_manifest_store_requires_exact_descriptor_not_config_or_index(self):
        for value in (None, {}, {"digest": q.CONFIG_DIGEST, "mediaType": q.MANIFEST_MEDIA_TYPE,
                                 "size": q.MANIFEST_BYTES},
                      {"digest": q.MANIFEST_DIGEST, "mediaType": "application/vnd.oci.image.index.v1+json",
                       "size": q.MANIFEST_BYTES},
                      {"digest": q.MANIFEST_DIGEST, "mediaType": q.MANIFEST_MEDIA_TYPE, "size": True}):
            with self.subTest(descriptor=value):
                row = inspected("oci_platform_manifest"); row["Descriptor"] = value
                with self.assertRaisesRegex(q.Qwen38OCIError, "descriptor_mismatch"):
                    q.verify_image(row)

    def test_labels_entrypoint_workdir_and_command_are_bound(self):
        for key, value in (("Entrypoint", ["python3"]), ("WorkingDir", "/tmp"),
                           ("Cmd", ["unreviewed"]), ("Labels", {}), ("Labels", None)):
            with self.subTest(key=key):
                row = inspected(); row["Config"][key] = value
                with self.assertRaises(q.Qwen38OCIError):
                    q.verify_image(row)
        for key in ("org.opencontainers.image.revision", "org.opencontainers.image.source"):
            row = inspected(); row["Config"]["Labels"][key] = "changed"
            with self.assertRaisesRegex(q.Qwen38OCIError, "source_mismatch"):
                q.verify_image(row)

    def test_receipt_cross_domain_substitution_or_missing_binding_is_rejected(self):
        e = q.verify_image(inspected())
        for key, value in (("image_id", q.MANIFEST_DIGEST),
                           ("image_id_domain", "oci_platform_manifest"),
                           ("config_digest", q.MANIFEST_DIGEST),
                           ("platform_manifest_digest", q.CONFIG_DIGEST),
                           ("image_reference", "lmsysorg/sglang@" + q.CONFIG_DIGEST),
                           ("source_revision", "0" * 40),
                           ("architecture", "arm64"), ("unknown", "extra")):
            bad = copy.deepcopy(e); bad[key] = value
            with self.subTest(key=key), self.assertRaises(q.Qwen38OCIError):
                q.validate_evidence(bad)
        for key in e:
            bad = copy.deepcopy(e); del bad[key]
            with self.subTest(missing=key), self.assertRaises(q.Qwen38OCIError):
                q.validate_evidence(bad)

    def test_container_cannot_substitute_other_valid_domain_or_mutable_reference(self):
        e = q.verify_image(inspected())
        for c in ({"Image": q.MANIFEST_DIGEST, "Config": {"Image": q.IMAGE_REFERENCE}},
                  {"Image": q.CONFIG_DIGEST, "Config": {"Image": "lmsysorg/sglang:v0.5.19-cu130"}},
                  {"Image": q.CONFIG_DIGEST, "Config": None}):
            with self.assertRaisesRegex(q.Qwen38OCIError, "container_image_mismatch"):
                q.validate_container_image(c, e)

    def test_metadata_bytes_cannot_be_synthesized_or_domain_swapped(self):
        for manifest, config in ((b"{}", b"{}"), (b"x" * q.MANIFEST_BYTES, b"y" * q.CONFIG_BYTES),
                                 (q.MANIFEST_DIGEST.encode(), q.CONFIG_DIGEST.encode()), (None, b"")):
            with self.assertRaisesRegex(q.Qwen38OCIError, "registry_bytes_mismatch"):
                q.verify_registry_bytes(manifest, config)


if __name__ == "__main__":
    unittest.main()
