"""Worker-only tests of native-route coverage assertions using explicit doubles.

No installed SGLang image or native handler executes here. Actual-image mode
loads the source-hash-verified application; these tests fault its assertions.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import secrets
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "f1e2_route_controls", ROOT / "tests/lifecycle/sglang_fixture/run_pinned_image.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class ModelInfoCoverageControls(unittest.TestCase):
    def setUp(self):
        self.sentinel, self.wrong = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.args = SimpleNamespace(tokenizer_path="/models", preferred_sampling_params=None,
                                    weight_version="worker-synthetic")
        self.server = SimpleNamespace(ServerStatus=SimpleNamespace(Starting="starting"))
        self.tokenizer = helper.SyntheticTokenizer(self.args, self.server)
        self.requests = []
        self.touch_on_rejection = False
        self.touch_on_success = True
        self.reject_status = 401
        self.leak_on_rejection = False
        self.bad_payload = False

        async def synthetic_endpoint():
            if self.touch_on_success:
                model = self.tokenizer.model_config
            else:
                model = self.tokenizer._model_config
            return {
                "model_path": "/models", "tokenizer_path": self.args.tokenizer_path,
                "is_generation": not self.bad_payload,
                "preferred_sampling_params": self.args.preferred_sampling_params,
                "weight_version": self.args.weight_version,
                "has_image_understanding": model.is_image_understandable_model,
                "has_audio_understanding": model.is_audio_understandable_model,
                "model_type": model.hf_config.model_type,
                "architectures": model.hf_config.architectures,
            }

        self.server.model_info = synthetic_endpoint
        owner = self

        class ExplicitWorkerASGIDouble:
            routes = [SimpleNamespace(path="/model_info", methods={"GET"},
                                      endpoint=synthetic_endpoint,
                                      dependant=SimpleNamespace(call=synthetic_endpoint))]

            async def __call__(self, scope, _receive, send):
                header = dict(scope["headers"]).get(b"authorization")
                correct = header == ("Bearer " + owner.sentinel).encode("ascii")
                owner.requests.append((scope["path"], header is not None, correct))
                if correct:
                    status, payload = 200, await synthetic_endpoint()
                else:
                    if owner.touch_on_rejection:
                        owner.tokenizer.model_config
                    status = owner.reject_status
                    payload = {"error": owner.sentinel if owner.leak_on_rejection else "unauthorized"}
                await send({"type": "http.response.start", "status": status, "headers": []})
                await send({"type": "http.response.body", "body": json.dumps(payload).encode(),
                            "more_body": False})

        self.app = ExplicitWorkerASGIDouble()

    def run_coverage(self):
        asyncio.run(helper.check_model_info_route(
            self.server, self.app, self.tokenizer, self.sentinel, self.wrong))

    def test_missing_wrong_correct_bearer_and_single_handler_entry_are_required(self):
        self.run_coverage()
        self.assertEqual(self.requests, [("/model_info", False, False),
                                        ("/model_info", True, False),
                                        ("/model_info", True, True)])
        self.assertEqual(self.tokenizer.model_config_reads, 1)

    def test_missing_duplicate_or_replaced_route_wiring_fails_before_requests(self):
        original = self.app.routes
        replacement = lambda: None
        cases = [[], original * 2,
                 [SimpleNamespace(path="/model_info", methods={"POST"},
                                  endpoint=self.server.model_info,
                                  dependant=SimpleNamespace(call=self.server.model_info))],
                 [SimpleNamespace(path="/model_info", methods={"GET"}, endpoint=replacement,
                                  dependant=SimpleNamespace(call=self.server.model_info))],
                 [SimpleNamespace(path="/model_info", methods={"GET"},
                                  endpoint=self.server.model_info,
                                  dependant=SimpleNamespace(call=replacement))]]
        for routes in cases:
            with self.subTest(route_count=len(routes)):
                self.app.routes = routes
                with self.assertRaisesRegex(helper.FixtureFailure,
                                            "native_model_info_route_wiring_missing"):
                    self.run_coverage()
                self.assertEqual(self.requests, [])

    def test_unauthorized_handler_entry_is_detected(self):
        self.touch_on_rejection = True
        with self.assertRaisesRegex(helper.FixtureFailure,
                                    "unauthorized_model_info_reached_handler"):
            self.run_coverage()

    def test_403_rejection_does_not_count_as_exact_native_contract(self):
        self.reject_status = 403
        with self.assertRaisesRegex(helper.FixtureFailure,
                                    "native_model_info_auth_rejection_failed"):
            self.run_coverage()

    def test_synthetic_success_without_handler_entry_is_detected(self):
        self.touch_on_success = False
        with self.assertRaisesRegex(helper.FixtureFailure,
                                    "native_model_info_handler_not_reached"):
            self.run_coverage()

    def test_changed_model_info_response_is_detected(self):
        self.bad_payload = True
        with self.assertRaisesRegex(helper.FixtureFailure, "native_model_info_response_changed"):
            self.run_coverage()

    def test_sentinel_in_rejection_evidence_is_detected_without_echo(self):
        self.leak_on_rejection = True
        with self.assertRaisesRegex(helper.FixtureFailure, "^sentinel_disclosure$"):
            self.run_coverage()


if __name__ == "__main__":
    unittest.main()
