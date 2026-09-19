"""Synthetic/offline command semantics; no containers, models or GPUs used."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import profiles, qwen_launcher as launch


class DefaultNone(SimpleNamespace):
    def __getattr__(self, key):
        return None


def synthetic_native_args(base, context, tp):
    args = DefaultNone()
    raw = launch.variant(base, context, tp)
    flags = dict(zip(raw[:-2:2], raw[1:-2:2]))
    numeric = {"port", "tp_size", "base_gpu_id", "gpu_id_step", "tokenizer_worker_num",
               "max_running_requests", "chunked_prefill_size", "max_mamba_cache_size", "context_length", "max_total_tokens"}
    for key, value in flags.items():
        key = key[2:].replace("-", "_")
        if key in numeric:
            value = int(value)
        if key == "mem_fraction_static":
            value = float(value)
        if key == "default_chat_template_kwargs":
            value = {"enable_thinking": False}
        setattr(args, key, value)
    args.fp8_gemm_runner_backend = args.fp8_gemm_backend
    args.disable_radix_cache = args.disable_overlap_schedule = True
    args.dp_size = args.pp_size = args.nnodes = 1
    args.node_rank = 0
    args.disaggregation_mode = "null"
    args.model_loader_extra_config = "{}"
    return args


class Profiles(unittest.TestCase):
    def test_all_twelve_commands_pinned_and_private(self):
        for p in ("G2", "G1", "Q2", "Q1"):
            for n in (4096, 16384, 65536):
                m = profiles.command_manifest(p, n)
                a = m["create_argv"]
                self.assertEqual(a[a.index("--publish") + 1].split(":")[0], "127.0.0.1")
                self.assertIn("--pull=never", a)
                self.assertEqual(len(m["gpu_uuids"]), int(p[1]))
                self.assertTrue(m["image"].startswith(("sha256:", "lmsysorg/sglang@sha256:")))
                self.assertEqual(m["status"], "DRY_RUN_NOT_EXECUTED")
                self.assertNotIn("--api-key", a)
                self.assertEqual(a[a.index("--restart") + 1], "no")

    def test_glm_fixed_n76_all_rungs_no_auto_fit(self):
        for p in ("G2", "G1"):
            commands = [profiles.command_manifest(p, n)["native_argv"] for n in (4096, 16384, 65536)]
            for args in commands:
                self.assertEqual(args[args.index("--n-cpu-moe") + 1], "76")
                self.assertEqual(args[args.index("--cache-type-k") + 1], "f16")
                self.assertEqual(args[args.index("--load-mode") + 1], "none")
                self.assertEqual(args[args.index("--fit") + 1], "off")
                self.assertEqual(args[args.index("--split-mode") + 1], "none" if p == "G1" else "layer")
                args[args.index("--ctx-size") + 1] = "CONTEXT"
            self.assertEqual(commands[0], commands[1])
            self.assertEqual(commands[1], commands[2])

    def test_qwen_pool_is_changed_and_tp_not_gpu_index(self):
        for p in ("Q1", "Q2"):
            m = profiles.command_manifest(p, 65536)
            a = m["native_argv"]
            for flag in ("--context-length", "--max-total-tokens"):
                self.assertEqual(a[a.index(flag) + 1], "65536")
            self.assertEqual(a[a.index("--tp-size") + 1], p[1])
            self.assertEqual(a[a.index("--base-gpu-id") + 1], "0")
            self.assertEqual(a[a.index("--kv-cache-dtype") + 1], "bfloat16")
            self.assertEqual(a[a.index("--quantization") + 1], "fp8")

    def test_mixed_requires_measured_caps_and_disjoint_resources(self):
        with self.assertRaises(ValueError):
            profiles.command_manifest("G1", 65536, mixed=True)
        caps = profiles.split_resources(400 * 1024**3, 40 * 1024**3, 860 * 1024**3)
        g = profiles.command_manifest("G1", 65536, mixed=True, ram_cap=caps["G1"])
        q = profiles.command_manifest("Q1", 16384, mixed=True, ram_cap=caps["Q1"])
        self.assertFalse(set(g["gpu_uuids"]) & set(q["gpu_uuids"]))
        gc, qc = profiles.cpu_set(g["guest_cpuset"]), profiles.cpu_set(q["guest_cpuset"])
        self.assertEqual((len(gc), len(qc), len(gc & qc)), (96, 16, 0))
        with self.assertRaisesRegex(ValueError, "reserve"):
            profiles.split_resources(700 * 1024**3, 100 * 1024**3, 860 * 1024**3)

    def test_cpu_baselines_and_matched_isolated_mixed_controls(self):
        for placement, count, cpuset in (("G2", 112, "0-111"), ("Q2", 112, "0-111"),
                                         ("G1", 96, "0-95"), ("Q1", 16, "96-111")):
            for capacity in (4096, 16384, 65536):
                modes = (False, True) if placement.endswith("1") else (False,)
                for mixed in modes:
                    manifest = profiles.command_manifest(placement, capacity, mixed=mixed,
                                                         ram_cap=500 * 1024**3 if mixed else None)
                    argv = manifest["create_argv"]
                    self.assertEqual(argv[argv.index("--cpuset-cpus") + 1], cpuset)
                    self.assertEqual(manifest["guest_cpuset"], cpuset)
                    self.assertEqual(manifest["guest_cpu_count"], count)
                    if placement.startswith("G"):
                        native = manifest["native_argv"]
                        for flag in ("--threads", "--threads-batch"):
                            self.assertEqual(native[native.index(flag) + 1], str(count))

    def test_unreviewed_optional_and_injected_identity_refused(self):
        for n in (131072, True, 1000000):
            with self.assertRaises(ValueError):
                profiles.command_manifest("G1", n)
        with self.assertRaises(ValueError):
            profiles.command_manifest("Q1", 4096, campaign="../production")

    def test_ladder_repeat_and_tool_budget(self):
        plan = profiles.trial_order()
        for p in ("G1", "G2", "Q1", "Q2"):
            r = [x for x in plan["trials"] if x["placement"] == p]
            self.assertEqual(len([x for x in r if x["case"] == "load_warmup"]), 3)
            self.assertEqual(len([x for x in r if x["case"] == "retrieval_anchor_repeat"]), 1)
            self.assertEqual(next(x["output_cap"] for x in r if x["case"] == "generation"), 512)


class BenchmarkLauncher(unittest.TestCase):
    def setUp(self):
        self.base = launch.pinned_base(profiles.ROOT / "scripts/runtime/sglang38_file_auth.py")

    def test_closed_tuple_and_canonical_args_only(self):
        for n in launch.CAPACITIES:
            for tp in (1, 2):
                self.setUp()
                argv = launch.bind_variant(self.base, n, tp)
                self.assertEqual(self.base.parse_options(argv)[0].context_length, str(n))
                for bad in (argv + ["--api-key", "synthetic-offline"], argv[::-1], argv[:-1]):
                    with self.assertRaises(self.base.LaunchError):
                        self.base.parse_options(bad)

    def test_reuses_raw_and_resolved_auth_cache_mode_guards(self):
        for n in launch.CAPACITIES:
            for tp in (1, 2):
                self.setUp()
                args = synthetic_native_args(self.base, n, tp)
                launch.bind_variant(self.base, n, tp)
                self.base.validate_server_args(args)
                args.grpc_worker_threads = 4
                args.cuda_graph_config = SimpleNamespace(decode=SimpleNamespace(backend="disabled"), prefill=SimpleNamespace(backend="disabled"))
                self.base.validate_server_args(args, resolved=True)
                for name, value in (("api_key", "synthetic-offline"), ("tp_size", 3), ("context_length", 1000000),
                                    ("kv_cache_dtype", "fp8_e4m3"), ("port", 30004), ("tool_server", "bad"),
                                    ("json_model_override_args", "{}"), ("served_model_name", "qwen3.8-27b")):
                    bad = DefaultNone(**vars(args))
                    setattr(bad, name, value)
                    with self.subTest(n=n, tp=tp, name=name), self.assertRaises(self.base.LaunchError):
                        self.base.validate_server_args(bad, resolved=True)

    def test_existing_production_module_remains_closed(self):
        with self.assertRaises(self.base.LaunchError):
            self.base.backend_argv(4096)
        with self.assertRaises(ValueError):
            launch.variant(self.base, 131072, 1)


if __name__ == "__main__":
    unittest.main()
