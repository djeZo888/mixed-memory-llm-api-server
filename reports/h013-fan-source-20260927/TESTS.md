# Focused offline verification

Commands (repository root; Python stdlib only):

```sh
python3 -m unittest discover -s tests -p 'test_h013_fan_boost.py' -v
python3 -m py_compile scripts/thermal/fan_boost.py
python3 scripts/thermal/fan_boost.py --help
git diff --check
```

`--help` exits before root/config/device checks. Compilation/import do not load
NVML. Tests replace hardware/state/jobs with fixtures and never contact live
hosts, load NVIDIA libraries or execute real setters. No broad suite/build.

Final focused test result and source commit are recorded in STATUS.json; the
captured focused output is test-output.txt. See README.md for NOT_TESTED hardware
and actual Linux/systemd behavior; a passing mock cannot establish deployment
availability or physical fan behavior.
