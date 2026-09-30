# SOURCE03 focused validation

Original service SHA256: `26f7b17da42bd07806c49d6477b3169efb5d33003d551cf5b6bb972742547556` (unchanged base910319da).

BEFORE command, after adding regression and before editing service:
```sh
python3 -B -m unittest discover -s tests/image_runtime -p test_operation_protocol.py -k test_warm_tuple_residency_publishes_and_operation_finally_completes -v
```
One expected error: real anchored save/finally refused `image_operation_changed`.

AFTER command, one affected-suite run:
```sh
python3 -B -m unittest discover -s tests/image_runtime -p 'test_*.py' -v
```
85 tests PASS, 0.640 seconds. Six persisted-field mutations still refused; the existing full start/warm fixture now includes tuple residency. No PYTHONPATH or environment overrides.

`git diff --check` PASS. Full before/after log exported as output/TESTS.log. No live acceptance or broad-repository claim.
