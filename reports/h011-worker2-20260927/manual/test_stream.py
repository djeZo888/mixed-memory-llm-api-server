#!/usr/bin/env python3
"""Run the existing H010 stream regressions on the exact H011 generated reader."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import prepare

if __name__=='__main__':
    source=prepare.FIXTURE.with_name('test_stream.py')
    spec=importlib.util.spec_from_file_location('h011_reused_stream_tests',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def test_body_sent_timestamp_is_after_request_boundary_without_hot_persist(self):
        harness=module.Harness([module.event({'content':'answer'},module.usage(1),'stop'),b'data: [DONE]\n'])
        row=harness.run()
        self.assertNotIn('request_body_sent_utc',harness.persisted[0]['request'])
        self.assertIn('request_body_sent_utc',row)
        self.assertEqual(row['request_body_sent_utc'],harness.persisted[-1]['request']['request_body_sent_utc'])
        self.assertEqual(len(harness.persisted),2)
    module.StreamTests.test_body_sent_timestamp_is_after_request_boundary_without_hot_persist=test_body_sent_timestamp_is_after_request_boundary_without_hot_persist
    with tempfile.TemporaryDirectory() as temp:
        output=Path(temp)/'candidate';prepare.prepare(output)
        module.SOURCE=output/'request_driver.py'
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
    raise SystemExit(0 if result.wasSuccessful() else 1)
