# Runtime device database fragment for atom_photon_parity_6.
# Replace channel numbers with the generated values from the matching bitstream.

device_db = {
    "core": {
        "type": "local",
        "module": "artiq.coredevice.core",
        "class": "Core",
        "arguments": {"host": "192.168.1.75", "ref_period": 1e-9},
    },
    "entangler": {
        "type": "local",
        "module": "entangler.atom_photon_parity_driver",
        "class": "AtomPhotonParityEntangler",
        "arguments": {"channel": 0},
    },
}

