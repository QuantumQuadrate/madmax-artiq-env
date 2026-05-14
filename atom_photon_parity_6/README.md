# Atom-Photon Parity 6 ARTIQ Runtime

This runtime folder contains:

- hardware-facing diagnostics for the `atom_photon_parity` custom Entangler
  helper, and
- a runnable wrapper for the full
  `qn_artiq_routines.subroutines.experiment_functions.atom_photon_parity_6_experiment`.

The wrapper keeps the parity-6 physics sequence in `repos/qn_artiq_routines` and
only adds an ARTIQ entry point inside this environment.

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

`device_db.py` imports the calibrated node-1 device database from
`repos/qn_artiq_routines/device_db/device_db_node1_with_edgecounters_calibrated.py`
and then adds the custom parity helper as `entangler`.

After generating/flashing a matching bitstream, update
`PARITY_HELPER_RTIO_CHANNEL` in `device_db.py` to the real RTIO channel assigned
to the helper.

## Setup

From this directory:

```bash
uv sync
```

The environment is seeded with `dataset_db.pyon` defaults from
`qn_artiq_routines/ExperimentVariables.py`, with `which_node = "alice"`. You can
edit `dataset_db.pyon` directly, run the QN `ExperimentVariables` experiment
from the dashboard, or override common parity-6 values from the wrapper GUI.

To start an ARTIQ master for this environment:

```bash
./run_artiq.sh
```

To run the full parity-6 experiment once from the command line:

```bash
./run_parity_6.sh
```

Common overrides can be passed through `artiq_run`:

```bash
./run_parity_6.sh n_measurements=10 target_780_HWP=12.5 target_780_QWP=0.0
```

The runnable wrapper is:

```text
repository/atom_photon_parity_6_experiment.py
```

It imports and calls:

```text
repos/qn_artiq_routines/subroutines/experiment_functions.py:
atom_photon_parity_6_experiment(self)
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

## Test Kasli With External Fake SPCM Pulses

For a test Kasli with two DIO cards, use one card for the parity helper and keep
the second DIO card as normal ARTIQ TTL outputs that simulate SPCM pulses.

Suggested wiring:

```text
DIO card 1 ttl12 output -> DIO card 0 helper input 0  # fake SPCM0
DIO card 1 ttl13 output -> DIO card 0 helper input 1  # fake SPCM1
```

Scope channels:

```text
CH1: fake SPCM0 pulse, ttl12
CH2: fake SPCM1 pulse, ttl13
CH3: helper branch-0 output
CH4: helper branch-1 output
```

Run one case at a time:

```bash
uv run python -I -m artiq.frontend.artiq_run \
  --device-db device_db.py --dataset-db dataset_db.pyon \
  -c AtomPhotonParity6ExternalSPCMSim \
  repository/atom_photon_parity_6_external_spcm_sim.py \
  'case="spcm0"'
```

Then repeat with:

```text
case="spcm1"
case="both"
case="none"
```

Expected outcomes:

| Case | Expected outcome | Expected branch output |
| --- | --- | --- |
| `spcm0` | `1`, `SPCM0_ONLY` | branch-0 output pulse only |
| `spcm1` | `2`, `SPCM1_ONLY` | branch-1 output pulse only |
| `both` | timeout/failure path | no branch pulse |
| `none` | timeout/failure path | no branch pulse |
 
The fake SPCM pulse defaults to 3 us after helper start, inside a 1-8 us gate.
Move `fake_spcm_delay_us` outside that gate to confirm that out-of-window pulses
are ignored.

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
