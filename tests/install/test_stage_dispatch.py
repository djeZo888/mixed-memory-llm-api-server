"""The public stage graph and real State/acquisition entrypoints in fixtures."""
from contextlib import ExitStack
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from install import main
from install.core import InstallError
from install.stage_state import AnchoredState
from install.storage_io import AnchoredRoot
from test_acquisition import Fixture


class DispatcherTests(Fixture):
    def state(self, anchor, source="source"):
        return AnchoredState(anchor, "state.json", self.config, "lock", source, self.guard, uid=self.uid)

    def stages(self, args, acquisition, events, done):
        def action(name):
            events.append("apply:" + name)
            done.add(name)
        def check(name):
            events.append("check:" + name)
            return name in done
        prereq = SimpleNamespace(recover_policy=lambda: events.append("recover_policy"),
            check_base=lambda: check("base"), apply_base=lambda: action("base"),
            check_driver=lambda: check("driver"), apply_driver=lambda: action("driver"))
        container = SimpleNamespace(check=lambda: check("container"), apply=lambda: action("container"),
            check_gpu=lambda: check("gpu_container"), apply_gpu=lambda: action("gpu_container"))
        runtime = SimpleNamespace(check=lambda: check("runtime"), apply=lambda: action("runtime"))
        storage = SimpleNamespace(guard=self.guard, root_payload_guard=self.guard, adopt=lambda: events.append("adopt"))
        with ExitStack() as stack:
            for name, value in (("install.prerequisites.Prerequisites", prereq), ("install.container.ContainerStage", container),
                                ("install.runtime.RuntimeStage", runtime), ("install.acquisition.AcquisitionStage", acquisition)):
                stack.enter_context(patch(name, return_value=value))
            return main.boundary_stages(self.config, args, None, storage, self.guard)

    def test_dispatcher_interruption_and_resume_uses_actual_acquisition(self):
        from test_acquisition import Response
        events, done = [], set()
        args = SimpleNamespace(command="apply", through="acquisition")
        self.overrides["nested/two.bin"] = lambda data, offset: Response(data[offset:offset+9], len(data), offset)
        with AnchoredRoot(self.roots["state"], self.guard, uid=self.uid) as anchor:
            with self.assertRaisesRegex(InstallError, "download_retry_limit"):
                self.state(anchor).run(self.stages(args, self.stage(), events, done))
            failed = json.loads((Path(self.roots["state"]) / "state.json").read_text())
            self.assertEqual(failed["stages"]["acquisition"]["status"], "failed")
            self.assertEqual(done, {"base", "driver", "container", "gpu_container", "runtime"})
            self.assertEqual([x for x in events if x.startswith("apply:")],
                             ["apply:" + x for x in ("base", "driver", "container", "gpu_container", "runtime")])
            self.overrides.clear()
            args.command = "resume"
            events.clear()
            result = self.state(anchor).run(self.stages(args, self.stage(), events, done))
            self.assertFalse(any(x.startswith("apply:") for x in events))
            self.assertEqual(result[-1], {"stage": "acquisition", "status": "complete"})
            self.assertTrue(self.stage().check())
            args.command = "verify"
            before = (Path(self.roots["state"]) / "state.json").read_bytes()
            self.state(anchor).run(self.stages(args, self.stage(), events, done), verify_only=True)
            self.assertEqual((Path(self.roots["state"]) / "state.json").read_bytes(), before)

    def test_alias_and_narrow_boundaries_use_exact_graph(self):
        for through, expected in (("container", ["storage", "base", "driver", "container"]),
                                  ("runtime", ["storage", "base", "driver", "container", "gpu_container", "runtime"]),
                                  ("models", ["storage", "base", "driver", "container", "gpu_container", "runtime", "acquisition"])):
            stages = self.stages(SimpleNamespace(command="verify", through=through), self.stage(), [], set())
            self.assertEqual([row[0] for row in stages], expected)

    def test_anchored_state_rejects_identity_drift_and_mount_loss(self):
        with AnchoredRoot(self.roots["state"], self.guard, uid=self.uid) as anchor:
            state = self.state(anchor)
            state.run([("storage", lambda: True, lambda: None)])
            with self.assertRaisesRegex(InstallError, "state_config_lock_or_source_changed"):
                self.state(anchor, source="changed")
            before = (Path(self.roots["state"]) / "state.json").read_bytes()
            self.present = False
            with self.assertRaisesRegex(InstallError, "fixture_mount_lost"):
                state.save()
            self.assertEqual((Path(self.roots["state"]) / "state.json").read_bytes(), before)

    def test_real_plan_reports_pins_bytes_effects_and_incomplete_status(self):
        from install.config import validate
        config = validate({"profile": "flagship-hybrid", "model_set": "glm,qwen"})
        args = main.parser().parse_args(["plan", "--fixture-host", str(REPO / "tests/install/fixtures/ubuntu-host.json")])
        plan = main.make_plan(config, args, None)
        self.assertEqual(plan["installer_status"], "INCOMPLETE_I1C_REQUIRED")
        self.assertFalse(plan["ready"])
        self.assertEqual(plan["pending_required_stages"], ["service", "acceptance"])
        details = plan["bounded_stage_plan"]
        self.assertEqual(sum(s["bytes"] for s in details["acquisition"]["selected"]), 547696839790)
        self.assertGreater(details["container"]["unique_dependency_download_bytes"], 0)
        self.assertEqual(len(details["runtimes"]), 2)
        self.assertEqual(details["unique_runtime_blob_transfer_bytes"], 16851434151)
        self.assertTrue(all(x["implementation"] == "available" for x in plan["stages"] if x["name"] in main.IMPLEMENTED))


if __name__ == "__main__":
    unittest.main()
