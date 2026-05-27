# Atom-Photon Parity 6 ARTIQ Runtime

This runtime folder contains:

- hardware-facing diagnostics for the `atom_photon_parity` custom entangler
  helper, and
- two dashboard wrappers for the full
  `qn_artiq_routines.subroutines.experiment_functions.atom_photon_parity_6_experiment`.

The parity-6 physics sequence is bundled locally under
`support/qn_artiq_routines` so this run environment can be used directly by
`artiq_master`/`artiq_dashboard` without relying on a checkout-relative symlink.

## Dashboard Experiments

Use these two files from `artiq_dashboard`:

| File | Class | Device DB | Purpose |
| --- | --- | --- | --- |
| `repository/atom_photon_parity_6_no_entangler.py` | `AtomPhotonParity6NoEntangler` | `device_db_no_entangler.py` | Full QN parity-6 sequence on a normal node-1 bitstream. |
| `repository/atom_photon_parity_6_with_entangler.py` | `AtomPhotonParity6WithEntanglerCore` | `device_db.py` | Full QN parity-6 sequence in the entangler-capable runtime; the helper is cleared and left in passthrough before the software sequence runs. |

The old entry point, `repository/atom_photon_parity_6_experiment.py`, remains as
a compatibility alias for `AtomPhotonParity6NoEntangler`.

## Expected Devices

The parity helper owns one DIO EEM, but that DIO must still appear as a normal
eight-channel ARTIQ card in `device_db.py`.

| Device | Physical line | Role |
| --- | --- | --- |
| `ttl0` | DIO0[0] | SPCM0 helper input and normal TTL input |
| `ttl1` | DIO0[1] | SPCM1 helper input and normal TTL input |
| `ttl2` | DIO0[2] | generic normal TTL input |
| `ttl3` | DIO0[3] | generic normal TTL input |
| `ttl4` | DIO0[4] | helper output 0 / normal TTL output |
| `ttl5` | DIO0[5] | helper output 1 / normal TTL output |
| `ttl6` | DIO0[6] | helper output 2 / normal TTL output |
| `ttl7` | DIO0[7] | helper output 3 / normal TTL output |

The `entangler` device must use:

```text
module = entangler.atom_photon_parity_driver
class = AtomPhotonParityEntangler
```

The matching gateware settings must keep `NUM_ENTANGLER_INPUT_SIGNALS = 2` and
`NUM_GENERIC_INPUT_SIGNALS = 2`. If the generic input count is lower, `ttl2`
and `ttl3` will disappear from the generated DDB and the full-DIO passthrough
contract is broken.

Regenerate/copy `device_db.py` only with the bitstream built from the same
`entangler_settings.toml`; the helper channel and all downstream channels move
when the exported TTL count changes.

## Setup

From this directory:

```bash
uv sync
```

The UV environment includes the ARTIQ stack, the local entangler driver,
`numpy`, `scipy`, `h5py`, `pyvisa`, and the other Python dependencies needed by
the bundled QN files.

The environment is seeded with `dataset_db.pyon` defaults from
`qn_artiq_routines/ExperimentVariables.py`, with `which_node = "alice"`. You can
edit `dataset_db.pyon` directly, run the QN `ExperimentVariables` experiment
from the dashboard, or override common parity-6 values from the wrapper GUI.

To start an ARTIQ master for the entangler-overlay bitstream:

```bash
./run_artiq.sh
```

For a normal no-entangler bitstream:

```bash
./run_artiq.sh --no-entangler
```

To run the full parity-6 experiment once from the command line:

```bash
./run_parity_6.sh
```

To use the entangler-aware runtime entry point:

```bash
./run_parity_6.sh --with-entangler
```

Common overrides can be passed through `artiq_run`:

```bash
./run_parity_6.sh n_measurements=10 target_780_HWP=12.5 target_780_QWP=0.0
```

The compatibility wrapper is:

```text
repository/atom_photon_parity_6_experiment.py
```

It imports and calls:

```text
repos/qn_artiq_routines/subroutines/experiment_functions.py:
atom_photon_parity_6_experiment(self)
```

## Device Map Warning

If the board boots with:

```text
error reading device map (Configuration key `device_map` not found)
```

the gateware and runtime are still up. That config key is only used to print
device names in RTIO error messages. Generate the matching blob from the same
device DB as the flashed image:

```bash
./make_device_map.py --device-db device_db.py --output device_map.bin
```

Then either copy it to `config/device_map.bin` on the SD card, or upload it to a
running core and reboot:

```bash
uv run python -I -m artiq.frontend.artiq_coremgmt \
  --device-db device_db.py config write -f device_map device_map.bin
uv run python -I -m artiq.frontend.artiq_coremgmt \
  --device-db device_db.py reboot
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

For a fixed two-cable setup on one DIO card, connect:

```text
entangler_output0 / DIO channel 4 -> entangler_input0 / DIO channel 0
entangler_output1 / DIO channel 5 -> entangler_input1 / DIO channel 1
```

Then run:

```bash
artiq_run -d device_db.py repository/atom_photon_parity_6_dual_loopback.py 'case="spcm0"'
artiq_run -d device_db.py repository/atom_photon_parity_6_dual_loopback.py 'case="spcm1"'
artiq_run -d device_db.py repository/atom_photon_parity_6_dual_loopback.py 'case="both"'
artiq_run -d device_db.py repository/atom_photon_parity_6_dual_loopback.py 'case="none"'
```

Expected outcomes are `1` for `spcm0`, `2` for `spcm1`, and timeout/failure
paths for `both` and `none`. Scope DIO channel 6 for the SPCM0 branch marker and
DIO channel 7 for the SPCM1 branch marker.

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

## Fast Loop Scope Test

Use this test to measure the gateware-only excitation loop and branch-marker
timing without the Python-side `5 us` padding delay from the full parity
experiment.

Suggested four-cable setup:

```text
helper output 0 / ttl4 / DIO0[4] -> helper input 0 / ttl0 / DIO0[0]
helper output 1 / ttl5 / DIO0[5] -> helper input 1 / ttl1 / DIO0[1]
helper output 2 / ttl6 / DIO0[6] -> monitor input ttl2
helper output 3 / ttl7 / DIO0[7] -> monitor input ttl3
```

Scope the same helper outputs directly:

```text
CH1: helper output 0, fake SPCM0 click
CH2: helper output 1, fake SPCM1 click
CH3: helper output 2, SPCM0-only branch marker
CH4: helper output 3, SPCM1-only branch marker
```

Run:

```bash
uv run python -I -m artiq.frontend.artiq_run \
  --device-db device_db.py --dataset-db dataset_db.pyon \
  -c AtomPhotonParity6FastLoopScope \
  repository/atom_photon_parity_6_fast_loop_scope.py \
  'case="spcm0"' 'repetitions=100'
```

Useful cases:

```text
case="spcm0"  # fake SPCM0, expect output 2 branch marker
case="spcm1"  # fake SPCM1, expect output 3 branch marker
case="both"   # fake both SPCMs, expect no branch marker and timeout/failure
case="none"   # no fake clicks, expect no branch marker and timeout/failure
```

Default timing is intentionally fast:

```text
attempt_period_ns = 128
fake_click_delay_ns = 16
gate_start_ns = 8
gate_width_ns = 16
branch_offset_ns = 96
branch_width_ns = 32
```

The printed `summary_average_loop_mu` is the hardware loop time. On the scope,
the branch marker should rise at:

```text
floor(click_ts / 8 ns) * 8 ns + branch_offset_ns
```

The current gateware uses the click's 8 ns coarse timestamp for branch outputs.

## Current Validation Notes

The matching gateware build description and runtime DDB were validated on
2026-05-25 with the main workspace `atom_photon_parity_6.yaml` config. The
expected overlay result is:

| Device group | RTIO channels |
| --- | --- |
| `ttl0` through `ttl7` | `0x000000` through `0x000007` |
| `ttl0_counter` through `ttl3_counter` | `0x000008` through `0x00000b` |
| `entangler0` / `entangler` | `0x00000c` |

`uv run pytest` in the main workspace passed the integration tests that check
the JSON description path, DIO overlay override wiring, and dry-run gateware
plan. Hardware loopback results should be recorded with the exact bitstream,
`device_db.py`, cable setup, case, and `summary_*` output printed by
`atom_photon_parity_6_fast_loop_scope.py`.

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
