"""Device database for the atom_photon_parity_6 runtime environment.

This starts from the calibrated node-1 QN device database, then adds the custom
atom-photon parity helper driver. After building/flashing the matching bitstream,
update ``PARITY_HELPER_RTIO_CHANNEL`` to the channel assigned to the Entangler
RTIO core in the generated device database.
"""

from pathlib import Path


PARITY_HELPER_RTIO_CHANNEL = 0


_ENV_ROOT = Path(__file__).resolve().parent
_WORKSPACE_ROOT = _ENV_ROOT.parents[2]
_QN_DEVICE_DB = (
    _WORKSPACE_ROOT
    / "repos"
    / "qn_artiq_routines"
    / "device_db"
    / "device_db_node1_with_edgecounters_calibrated.py"
)

_namespace: dict[str, object] = {}
exec(compile(_QN_DEVICE_DB.read_text(encoding="utf-8"), str(_QN_DEVICE_DB), "exec"), _namespace)
device_db = dict(_namespace["device_db"])

device_db["entangler"] = {
    "type": "local",
    "module": "entangler.atom_photon_parity_driver",
    "class": "AtomPhotonParityEntangler",
    "arguments": {"channel": PARITY_HELPER_RTIO_CHANNEL},
}
