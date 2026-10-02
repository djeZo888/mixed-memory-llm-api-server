"""SOURCE_ONLY synthetic roster/readback fixtures; never live qualification."""
import copy
import unittest
from unittest import mock

import control
import normal_handoff
import observer


def fixture():
    roster = {
        "general": ["qwen0", "qwen1", "mimo"],
        "vision": ["interpretation", "ocr"],
        "generation": False,
    }
    protected = [
        {
            "serviceId": service,
            "id": str(index + 1) * 64,
            "birth": {"pid": 100 + index, "startTicks": 200 + index, "cgroup": "/synthetic/general/" + service},
            "image": "sha256:" + "a" * 64,
            "devices": [{"DeviceIDs": ["SOURCE_ONLY_GENERAL_GPU_" + service]}],
        }
        for index, service in enumerate(roster["general"])
    ]
    resources = [
        {
            "role": role,
            "id": str(index + 4) * 64,
            "birth": {"pid": 400 + index, "startTicks": 500 + index, "cgroup": "/synthetic/vision/" + role},
            "image": "sha256:" + "b" * 64,
            "devices": [{"DeviceIDs": [observer.GPU]}],
            "attachBirth": {"pid": 600 + index},
        }
        for index, role in enumerate(roster["vision"])
    ]
    resources.extend({"role": role, "id": role} for role in ("service", "ingress", "network"))
    graph = {"runtime": {"enabledServices": roster}, "rootOwnerEvidence": {"protectedInstances": protected}}
    record = {
        "enabledServices": copy.deepcopy(roster),
        "protectedInstances": copy.deepcopy(protected),
        "visionInstances": [{key: item[key] for key in ("role", "id", "birth", "image", "devices")} for item in resources[:2]],
        "instanceCount": 5,
        "concurrentOperation": True,
        "minimumFreeFraction": 0.07,
    }
    return graph, resources, record


class EnabledRosterTests(unittest.TestCase):
    def test_explicit_five_instance_roster_and_legacy_four_are_distinct(self):
        graph, _, _ = fixture()
        self.assertEqual(control.enabled_roster(graph), graph["runtime"]["enabledServices"])
        self.assertEqual(control.protected_roster(graph), graph["rootOwnerEvidence"]["protectedInstances"])
        legacy = {"rootOwnerEvidence": {"otherFourInstances": [{"id": str(i)} for i in range(4)]}}
        self.assertIsNone(control.enabled_roster(legacy))
        self.assertEqual(control.protected_roster(legacy), legacy["rootOwnerEvidence"]["otherFourInstances"])
        legacy["rootOwnerEvidence"]["otherFourInstances"].pop()
        with self.assertRaises(control.Refused):
            control.protected_roster(legacy)

    def test_explicit_roster_rejects_missing_unexpected_and_generation_fields(self):
        mutations = [
            ("missing", lambda r: r.pop("generation")),
            ("extra", lambda r: r.update(extra=True)),
            ("generation_on", lambda r: r.update(generation=True)),
            ("generation_integer", lambda r: r.update(generation=0)),
            ("general_missing", lambda r: r["general"].pop()),
            ("general_duplicate", lambda r: r["general"].__setitem__(2, "qwen0")),
            ("general_unexpected", lambda r: r["general"].__setitem__(2, "generator")),
            ("vision_missing", lambda r: r["vision"].pop()),
            ("vision_duplicate", lambda r: r["vision"].__setitem__(1, "interpretation")),
            ("vision_unexpected", lambda r: r["vision"].__setitem__(1, "generation")),
        ]
        for name, mutate in mutations:
            graph, _, _ = fixture()
            mutate(graph["runtime"]["enabledServices"])
            with self.subTest(case=name), self.assertRaises(control.Refused):
                control.enabled_roster(graph)

    def test_explicit_roster_cannot_fall_back_to_legacy_owners(self):
        graph, _, _ = fixture()
        graph["rootOwnerEvidence"] = {"otherFourInstances": [{"id": str(i)} for i in range(4)]}
        with self.assertRaises(control.Refused):
            control.protected_roster(graph)

    def test_explicit_null_roster_cannot_inherit_legacy_authority(self):
        graph, _, _ = fixture()
        graph["runtime"]["enabledServices"] = None
        graph["rootOwnerEvidence"]["otherFourInstances"] = [{"id": str(i)} for i in range(4)]
        with self.assertRaises(control.Refused):
            control.enabled_roster(graph)

    def test_protected_owners_require_three_unique_complete_container_tuples(self):
        mutations = [
            ("missing", lambda p: p.pop()),
            ("extra", lambda p: p.append(copy.deepcopy(p[0]))),
            ("duplicate_service", lambda p: p[1].update(serviceId=p[0]["serviceId"])),
            ("unknown_service", lambda p: p[2].update(serviceId="generation")),
            ("duplicate_id", lambda p: p[1].update(id=p[0]["id"])),
            ("short_id", lambda p: p[0].update(id="a" * 12)),
            ("nonhex_id", lambda p: p[0].update(id="z" * 64)),
            ("missing_birth", lambda p: p[0].pop("birth")),
            ("empty_birth", lambda p: p[0].update(birth={})),
            ("empty_image", lambda p: p[0].update(image="")),
            ("empty_devices", lambda p: p[0].update(devices=[])),
        ]
        for name, mutate in mutations:
            graph, _, _ = fixture()
            mutate(graph["rootOwnerEvidence"]["protectedInstances"])
            with self.subTest(case=name), self.assertRaises(control.Refused):
                control.protected_roster(graph)

    def test_observer_requires_each_exact_original_running_container(self):
        graph, _, _ = fixture()
        expected = graph["rootOwnerEvidence"]["protectedInstances"]
        observed = {item["id"]: {"birth": item["birth"], "value": {"image": item["image"], "devices": item["devices"], "running": True}} for item in expected}
        with mock.patch.object(observer, "exact_container", side_effect=lambda cid: observed[cid]) as inspect:
            self.assertEqual(observer.protected_instances(graph, {}), expected)
            self.assertEqual(inspect.call_args_list, [mock.call(item["id"]) for item in expected])
        mutations = [
            ("birth", lambda value: value.update(birth={"pid": 999})),
            ("image", lambda value: value["value"].update(image="changed")),
            ("devices", lambda value: value["value"].update(devices=[])),
            ("stopped", lambda value: value["value"].update(running=False)),
            ("missing", lambda value: value.clear()),
        ]
        for name, mutate in mutations:
            changed = copy.deepcopy(observed)
            mutate(changed[expected[2]["id"]])
            with self.subTest(case=name), mock.patch.object(observer, "exact_container", side_effect=lambda cid: changed[cid]), self.assertRaises(control.Refused):
                observer.protected_instances(graph, {})

    def test_enabled_evidence_replaces_only_legacy_six_resident_requirement(self):
        graph, _, _ = fixture()
        legacy = set(normal_handoff.required_evidence({}))
        enabled = set(normal_handoff.required_evidence(graph))
        self.assertIn("sixResident", legacy)
        self.assertNotIn("enabledResident", legacy)
        self.assertEqual(enabled, (legacy - {"sixResident"}) | {"enabledResident"})

    def test_enabled_residency_accepts_exact_five_and_headroom_boundary(self):
        graph, resources, record = fixture()
        normal_handoff.validate_enabled_residency(record, graph, resources)
        record["minimumFreeFraction"] = 1.0
        normal_handoff.validate_enabled_residency(record, graph, resources)

    def test_enabled_residency_rejects_mutated_owners_roles_counts_and_headroom(self):
        mutations = [
            ("missing_roster", lambda r: r.pop("enabledServices")),
            ("generation_on", lambda r: r["enabledServices"].update(generation=True)),
            ("generation_integer", lambda r: r["enabledServices"].update(generation=0)),
            ("protected_missing", lambda r: r["protectedInstances"].pop()),
            ("protected_birth", lambda r: r["protectedInstances"][0]["birth"].update(startTicks=999)),
            ("vision_missing", lambda r: r["visionInstances"].pop()),
            ("vision_duplicate", lambda r: r["visionInstances"].__setitem__(1, copy.deepcopy(r["visionInstances"][0]))),
            ("vision_wrong_id", lambda r: r["visionInstances"][0].update(id="f" * 64)),
            ("vision_wrong_image", lambda r: r["visionInstances"][0].update(image="changed")),
            ("vision_wrong_devices", lambda r: r["visionInstances"][0].update(devices=[])),
            ("vision_extra", lambda r: r["visionInstances"].append({"role": "generation"})),
            ("legacy_six", lambda r: r.update(instanceCount=6)),
            ("missing_count", lambda r: r.pop("instanceCount")),
            ("not_concurrent", lambda r: r.update(concurrentOperation=False)),
            ("concurrency_integer", lambda r: r.update(concurrentOperation=1)),
            ("low_headroom", lambda r: r.update(minimumFreeFraction=0.069)),
            ("high_headroom", lambda r: r.update(minimumFreeFraction=1.01)),
            ("nan_headroom", lambda r: r.update(minimumFreeFraction=float("nan"))),
            ("infinite_headroom", lambda r: r.update(minimumFreeFraction=float("inf"))),
            ("boolean_headroom", lambda r: r.update(minimumFreeFraction=True)),
        ]
        for name, mutate in mutations:
            graph, resources, record = fixture()
            mutate(record)
            with self.subTest(case=name), self.assertRaises(control.Refused):
                normal_handoff.validate_enabled_residency(record, graph, resources)


if __name__ == "__main__":
    unittest.main()
