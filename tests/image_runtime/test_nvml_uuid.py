"""AST-only regression for the single pinned SGLang NVML UUID repair."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


PATCH = Path(__file__).resolve().parents[2] / "scripts/image_runtime/patches/sglang-nvml-uuid.patch"
# Exact function preimage from pinned commit0cd8be351; no SGLang/CUDA imports.
PINNED_FUNCTION = 'def device_id_to_physical_device_id(device_id: int) -> int:\n    if "CUDA_VISIBLE_DEVICES" in os.environ:\n        device_ids = os.environ["CUDA_VISIBLE_DEVICES"].split(",")\n        if device_ids == [""]:\n            msg = (\n                "CUDA_VISIBLE_DEVICES is set to empty string, which means"\n                " GPU support is disabled. If you are using ray, please unset"\n                " the environment variable `CUDA_VISIBLE_DEVICES` inside the"\n                " worker/actor. "\n                "Check https://github.com/vllm-project/vllm/issues/8402 for"\n                " more information."\n            )\n            raise RuntimeError(msg)\n        physical_device_id = device_ids[device_id]\n        return int(physical_device_id)\n    else:\n        return device_id\n'
UUID = "GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23"


def patched_function(environ, nvml):
    lines = PATCH.read_text().splitlines(keepends=True)
    hunks = [index for index, line in enumerate(lines) if line.startswith("@@ ")]
    if len(hunks) != 1:
        raise AssertionError("Expected the one reviewed UUID repair hunk")
    hunk = lines[hunks[0] + 1:]
    original = "".join(line[1:] for line in hunk if line.startswith((" ", "-")))
    replacement = "".join(line[1:] for line in hunk if line.startswith((" ", "+")))
    if PINNED_FUNCTION.count(original) != 1:
        raise AssertionError("Patch does not match the pinned helper preimage")
    module = ast.parse(PINNED_FUNCTION.replace(original, replacement, 1))
    if len(module.body) != 1 or not isinstance(module.body[0], ast.FunctionDef):
        raise AssertionError("Repair must retain one isolated helper function")
    namespace = {"os": SimpleNamespace(environ=environ), "pynvml": nvml}
    exec(compile(module, str(PATCH), "exec"), namespace)
    return namespace["device_id_to_physical_device_id"]


class NvmlUuidRepair(unittest.TestCase):
    def test_uuid_uses_resolved_nvml_index_and_balances_context(self):
        nvml = Mock()
        nvml.nvmlDeviceGetIndex.return_value = 7
        function = patched_function({"CUDA_VISIBLE_DEVICES": UUID}, nvml)
        self.assertEqual(function(0), 7)
        self.assertEqual([item[0] for item in nvml.mock_calls], [
            "nvmlInit", "nvmlDeviceGetHandleByUUID", "nvmlDeviceGetIndex", "nvmlShutdown",
        ])
        nvml.nvmlDeviceGetHandleByUUID.assert_called_once_with(UUID)
        nvml.nvmlDeviceGetIndex.assert_called_once_with(nvml.nvmlDeviceGetHandleByUUID.return_value)

    def test_lookup_failure_propagates_and_still_shuts_down(self):
        nvml = Mock()
        nvml.nvmlDeviceGetHandleByUUID.side_effect = LookupError("unknown device")
        function = patched_function({"CUDA_VISIBLE_DEVICES": UUID}, nvml)
        with self.assertRaises(LookupError):
            function(0)
        nvml.nvmlShutdown.assert_called_once_with()
        nvml.nvmlDeviceGetIndex.assert_not_called()

    def test_numeric_unset_and_empty_semantics_are_preserved(self):
        nvml = Mock()
        self.assertEqual(patched_function({"CUDA_VISIBLE_DEVICES": "4,1"}, nvml)(1), 1)
        self.assertEqual(patched_function({}, nvml)(3), 3)
        with self.assertRaisesRegex(RuntimeError, "GPU support is disabled"):
            patched_function({"CUDA_VISIBLE_DEVICES": ""}, nvml)(0)
        self.assertEqual(nvml.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
