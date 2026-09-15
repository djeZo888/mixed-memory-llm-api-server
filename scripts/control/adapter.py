"""Production binding gate.

The reviewed U1 base has no borrowed-lease Manager loader. An API extraction is
not reviewed source. There is deliberately no mock, legacy Manager constructor,
subprocess, environment override or best-effort production fallback here.
"""
from .protocol import ControlError

GAPS = (
    "reviewed_l1_loader_and_borrowed_dispatch",
    "reviewed_i1r_shared_package_admission",
    "protected_registered_catalog_and_readiness_translation",
    "anchored_operation_journal_binding",
    "bounded_manager_call_deadlines",
    "trusted_recovery_observation_and_generation_binding",
)


def production_application():
    raise ControlError("production_adapter_unavailable")
