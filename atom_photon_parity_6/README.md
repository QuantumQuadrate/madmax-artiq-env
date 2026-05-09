# Atom-Photon Parity 6 ARTIQ Runtime

This runtime folder contains hardware-facing experiments for the
`atom_photon_parity` custom Entangler mode used to test the timing-critical
section of `atom_photon_parity_6_experiment`.

## Expected Devices

The generated config assumes one DIO EEM:

| Device | Suggested signal |
| --- | --- |
| `entangler_input0` | `SPCM0` or loopback into the SPCM0 input |
| `entangler_input1` | `SPCM1` or loopback into the SPCM1 input |
| `entangler_output0` | fake photon pulse or FORT blanking debug |
| `entangler_output1` | branch debug pulse |
| `entangler_output2` | microwave switch debug pulse |
| `entangler_output3` | MW+RF/debug branch pulse |

The `entangler` device must use:

```text
module = entangler.atom_photon_parity_driver
class = AtomPhotonParityEntangler
```

## Run Order

Start with no loopbacks and no detectors connected:

```bash
artiq_run -d device_db.py repository/atom_photon_parity_6_smoke.py
artiq_run -d device_db.py repository/atom_photon_parity_6_no_click.py
```

Then add one loopback at a time:

```text
entangler_output0 -> entangler_input0  # for SPCM0 loopback
entangler_output0 -> entangler_input1  # for SPCM1 loopback
```

Run:

```bash
artiq_run -d device_db.py repository/atom_photon_parity_6_spcm0_loopback.py
artiq_run -d device_db.py repository/atom_photon_parity_6_spcm1_loopback.py
artiq_run -d device_db.py repository/atom_photon_parity_6_timing_scan.py
artiq_run -d device_db.py repository/atom_photon_parity_6_stress.py
artiq_run -d device_db.py repository/atom_photon_parity_6_benchmark.py
```

The loopback files use output 0 as a synthetic photon pulse. They are meant to
prove timestamp capture and branch selection before using the real SPCM signals.

## Outcome Codes

| Code | Meaning |
| --- | --- |
| 0 | no terminal single-click outcome |
| 1 | `SPCM0_ONLY` |
| 2 | `SPCM1_ONLY` |
| 3 | both SPCMs captured |

Important status bits:

| Bit | Meaning |
| --- | --- |
| 0 | ready |
| 1 | running |
| 2 | success |
| 3 | timeout |
| 4 | invalid configuration |
| 8-9 | captured SPCM bitfield |
| 16-17 | outcome |

## Safety Notes

These experiments can toggle TTL outputs. Keep the test outputs disconnected
from laser, microwave, RF, or FORT control hardware until the bitstream and
polarity are confirmed on a scope.

When the helper is disabled with `entangler.configure(False)`, output pads should
fall back to normal ARTIQ TTL passthrough.

