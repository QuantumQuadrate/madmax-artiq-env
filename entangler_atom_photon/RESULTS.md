# Atom-Photon Entangler Hardware Timing Results

This document records the hardware checks and timing comparison run from the
`entangler_atom_photon` ARTIQ environment.

## Setup

- ARTIQ environment: `entangler_atom_photon/.venv`
- ARTIQ version: `ARTIQ v7.0`
- Core address from `device_db.py`: `192.168.1.129`
- Core reachability: ping passed with 0 percent packet loss
- ARTIQ reference period in the device DB: `1e-09`, so `1 mu = 1 ns`

Required physical loopback:

```text
ttl5 / dio0[5] -> ttl0 / dio0[0]
```

Recommended scope probes for the timing comparison:

```text
Scope CH1: ttl5 / dio0[5]   input-event source / excitation pulse
Scope CH2: ttl6 / dio0[6]   branch/action output
```

No additional TTL-to-TTL loopback was required for the runs below. If you want
ARTIQ to measure the actual physical `ttl6` output edge instead of relying on
the programmed gateware action timestamp, add a separate measurement loopback
from `ttl6` to a free TTL input and use that input only for timestamping.

## Local Compatibility Fixes

The atom-photon environment needed a few local fixes before the experiments
would run on this installed ARTIQ v7 runtime.

1. `device_db.py`

   Removed unsupported `Core` constructor arguments:

   ```text
   analyzer_proxy
   satellite_cpu_targets
   ```

   This ARTIQ runtime reports:

   ```text
   Core.__init__(self, dmgr, host, ref_period, ref_multiplier=8, target='rv32g')
   ```

2. `repository/ttl5_to_ttl0_loopback_check.py`

   Cast MU arguments to `np.int64` before using them with `delay_mu()` and
   `pulse_mu()`, and added realtime slack before the LED pulse.

3. `repository/atom_photon_gateware_smoke.py`

   Added `core.break_realtime()` between entangler register reads to avoid RTIO
   underflow during post-run status collection.

4. `repository/cpu_branch_timing_comparison.py`

   Cast configurable MU arguments to `np.int64` before scheduling CPU-side TTL
   output pulses.

5. `repository/atom_photon_hardware_branch_timing.py`

   Added concurrent `ttl0.gate_rising(2 * us)` while `entangler0.run_mu()` is
   active. On this bitstream/PHY path, the entangler only detected the looped
   fake SPCM event when the ARTIQ input gate was armed concurrently.

   Also added realtime breaks between entangler register reads and allowed the
   branch action offset argument to go down to `32 mu`.

## Commands

All commands were run from:

```bash
cd /home/jrydberg/Documents/Projects/Artiq_envs/madmax-artiq-env/entangler_atom_photon
```

Direct TTL loopback:

```bash
.venv/bin/artiq_run --device-db device_db.py repository/ttl5_to_ttl0_loopback_check.py
```

Gateware smoke test:

```bash
.venv/bin/artiq_run --device-db device_db.py repository/atom_photon_gateware_smoke.py
```

CPU branch timing:

```bash
.venv/bin/artiq_run --device-db device_db.py repository/cpu_branch_timing_comparison.py repeats=10 cpu_action_offset_mu=890
```

Atom-photon gateware branch timing:

```bash
.venv/bin/artiq_run --device-db device_db.py repository/atom_photon_hardware_branch_timing.py repeats=10 action_offset_mu=32
```

## Direct TTL5 To TTL0 Loopback

The direct loopback test passed on all five repeats.

```text
loopback ttl0_minus_ttl5_mu: 154
loopback ttl0_minus_ttl5_mu: 154
loopback ttl0_minus_ttl5_mu: 154
loopback ttl0_minus_ttl5_mu: 153
loopback ttl0_minus_ttl5_mu: 154
```

Result:

```text
ttl5 -> ttl0 physical/RTIO timestamp offset: 153-154 mu
```

With `1 mu = 1 ns`, this is approximately:

```text
153-154 ns
```

## Atom-Photon Gateware Smoke Test

The smoke test completed successfully with no photon input.

Representative output:

```text
atom-photon smoke status 9
atom-photon smoke outcome 0
atom-photon smoke done_reason 2
atom-photon smoke attempts 1
atom-photon smoke spcm0_ts 0
atom-photon smoke spcm1_ts 0
atom-photon smoke chosen_ts 0
```

Interpretation:

```text
outcome 0      = NEITHER
done_reason 2 = NEITHER terminal path
attempts 1    = one configured attempt completed
```

This is the expected result for the conservative smoke test with no SPCM event.

## CPU Branch Timing

The CPU timing test follows the software path:

1. Schedule a `ttl5` pulse.
2. Detect the looped edge on `ttl0`.
3. Read the timestamp in the Python kernel.
4. Branch in CPU/kernel code.
5. Schedule `ttl6` at `click_mu + cpu_action_offset_mu`.

Passing CPU timing points:

```text
cpu_action_offset_mu=1000: passed
cpu_action_offset_mu=950:  passed
cpu_action_offset_mu=900:  passed
cpu_action_offset_mu=890:  passed 10/10
```

Failing CPU timing points:

```text
cpu_action_offset_mu=880: underflow
cpu_action_offset_mu=875: underflow
cpu_action_offset_mu=850: underflow
cpu_action_offset_mu=800: underflow
```

The `890 mu` confirmation run passed ten repeats:

```text
ttl0_minus_ttl5_mu: 154 on all 10 repeats
ttl6_offset_from_click_mu: 890 on all 10 repeats
```

Result:

```text
Minimum reliable CPU click-to-ttl6 schedule offset in this run: about 890 mu
```

With `1 mu = 1 ns`:

```text
CPU path minimum: about 890 ns
```

## Atom-Photon Gateware Branch Timing

The atom-photon gateware timing test uses the entangler path:

1. The entangler drives output bit 1, exported as `ttl5`.
2. `ttl5` is looped back to `ttl0` as a fake SPCM0 click.
3. The atom-photon entangler detects the SPCM0-only event.
4. Branch 0 schedules action output bit 2, exported as `ttl6`.

Important implementation detail:

```text
ttl0.gate_rising(2 * us) is armed concurrently with entangler0.run_mu().
```

Without that concurrent ARTIQ input gate, this bitstream/PHY setup reported
`NEITHER` even though the direct TTL loopback worked.

The `32 mu` hardware action offset run passed ten repeats:

```text
outcome:                 1 on all 10 repeats
done_reason:             1 on all 10 repeats
attempts:                1 on all 10 repeats
chosen_ts_mu:            132-133
ttl6_expected_ts_mu:     164-165
logical_click_to_ttl6_mu: 32
```

Interpretation:

```text
outcome 1      = SPCM0_ONLY
done_reason 1 = SUCCESS
chosen_ts_mu  = detected SPCM timestamp in entangler time
ttl6_expected_ts_mu = chosen_ts_mu + action_offset_mu
```

Result:

```text
Programmed gateware click-to-ttl6 action offset tested successfully: 32 mu
```

With `1 mu = 1 ns`:

```text
Atom-photon gateware action offset: 32 ns
```

The `run_mu()` completion timestamp is later than the TTL6 action start because
the hardware action has a programmed duration and the driver returns on the
entangler completion event. In the `32 mu` run, `finished_at_mu` occurred about
`132 mu` after the CPU monitor timestamp of the looped `ttl0` edge.

## Comparison

Best observed CPU path:

```text
CPU click-to-ttl6 scheduling offset: about 890 mu
```

Best observed atom-photon gateware path:

```text
Gateware programmed click-to-ttl6 action offset: 32 mu
```

Difference:

```text
890 mu - 32 mu = 858 mu
```

With `1 mu = 1 ns`:

```text
Atom-photon gateware action is about 858 ns faster than the CPU branch path.
```

## Final Result

The new atom-photon entangler gateware successfully detected the fake SPCM0
event from the `ttl5 -> ttl0` loopback and scheduled the branch action on
`ttl6`.

For the time-critical TTL action itself, the gateware path was much faster than
the CPU path in this test:

```text
CPU path:                 about 890 ns
Atom-photon gateware path: about 32 ns
Improvement:              about 858 ns faster
```

For a purely software-visible result, `entangler0.run_mu()` returns later than
the TTL6 action start. The speedup matters most when the next time-critical
operation is kept inside gateware, as it is here with the branch action table.
