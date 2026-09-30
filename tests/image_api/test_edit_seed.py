"""Fresh default edit seed, truthful metadata, unchanged explicit seeds."""
import unittest
from unittest.mock import patch

from test_handlers import Backend, config, fixture, png, profile
from image_api import protocol


class EditSeed(unittest.IsolatedAsyncioTestCase):
    async def test_missing_edit_seed_drawn_once_and_reported_exactly(self):
        native = Backend()
        with patch.object(protocol.secrets, 'randbits', return_value=3141592653) as draw:
            async with fixture(backend=native) as (client, _, _, _):
                response = await client.post('/v1/images/edits', data={'prompt': 'x'},
                                             files={'image': ('input.png', png())})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['data'][0]['seed'], 3141592653)
        draw.assert_called_once_with(32)
        self.assertEqual(len(native.calls), 1)
        self.assertEqual(native.calls[0]['seed'], 3141592653)
        self.assertEqual(native.calls[0]['prompt'], 'x')
        self.assertEqual(native.calls[0]['true_cfg_scale'], 1)
        self.assertEqual(native.calls[0]['num_inference_steps'], 40)

    async def test_explicit_seed_boundaries_are_preserved_and_reported(self):
        native = Backend()
        with patch.object(protocol.secrets, 'randbits', side_effect=AssertionError('unexpected draw')):
            async with fixture(backend=native) as (client, _, _, _):
                for seed in (0, 42, 2**63 - 1):
                    response = await client.post('/v1/images/edits', data={'prompt': 'x', 'seed': str(seed)},
                                                 files={'image': ('input.png', png())})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()['data'][0]['seed'], seed)
                    self.assertEqual(native.calls[-1]['seed'], seed)

    async def test_generation_seed_and_response_contract_unchanged(self):
        native = Backend()
        with patch.object(protocol.secrets, 'randbits', side_effect=AssertionError('unexpected draw')):
            async with fixture(backend=native) as (client, _, _, _):
                for fields in ({'prompt': 'x'}, {'prompt': 'x', 'seed': 42}):
                    response = await client.post('/v1/images/generations', json=fields)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(set(response.json()['data'][0]), {'b64_json'})
        self.assertNotIn('seed', native.calls[0])
        self.assertEqual(native.calls[1]['seed'], 42)

    async def test_unqualified_edit_never_draws_or_dispatches(self):
        native = Backend()
        with patch.object(protocol.secrets, 'randbits', side_effect=AssertionError('unexpected draw')):
            async with fixture(backend=native, qualification=config([profile('generation', 0)])) as (client, _, _, _):
                response = await client.post('/v1/images/edits', data={'prompt': 'x'},
                                             files={'image': ('input.png', png())})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['error']['code'], 'unqualified_profile')
        self.assertEqual(native.calls, [])

    async def test_native_failure_does_not_redraw_or_retry(self):
        native = Backend(fail=True)
        with patch.object(protocol.secrets, 'randbits', return_value=7) as draw:
            async with fixture(backend=native) as (client, _, _, _):
                response = await client.post('/v1/images/edits', data={'prompt': 'x'},
                                             files={'image': ('input.png', png())})
                self.assertEqual(response.status_code, 502)
        draw.assert_called_once_with(32)
        self.assertEqual(len(native.calls), 1)
        self.assertEqual(native.calls[0]['seed'], 7)


if __name__ == '__main__':
    unittest.main()
