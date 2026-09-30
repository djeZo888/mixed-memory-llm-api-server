# Reviewed publication subset

Source worker report commit: `09d42aa425ae290ac58007fbfb7024f832d8e7b6`.
The eight selected report files retain their exact worker contents; the actual
post-exit coordinator receipt is included separately. Detailed boundary,
settlement and staging traces remain in the private durable task directory.

In COMPACTION-RESULT.json and its nested copy in RESULT.json, the historical
scope text says recall/cold pending. Final outcomes are recall PASS and cold
resume FAIL, as recorded in the separate final cases. The final native wrapper
exit is in COORDINATOR-TERMINAL.json; the worker could not attest its own future
exit when it wrote RESULT.json. No unexecuted workflow is qualified.
