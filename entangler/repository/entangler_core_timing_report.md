# Entangler Core Timing Report

## Scope

This report summarizes the local timing diagnostics comparing the ARTIQ CPU TTL
timestamp branch against the entangler core for the current one-DIO loopback
setup.

The confirmed loopbacks are:

```text
ttl5 output -> ttl1 input    entangler output 1 -> entangler input 1
ttl4 output -> ttl3 input    entangler output 0 -> entangler input 3
```

The runtime settings must match the flashed bitstream:

```toml
NUM_PATTERNS_ALLOWED = 2
```

With four entangler inputs, this makes the pattern enable shift equal to `8`.
When runtime settings used `NUM_PATTERNS_ALLOWED = 4`, the input timestamp
registers latched valid clicks, but the pattern matcher did not assert success.

## What Was Measured

The benchmark compares three timing quantities:

```text
CPU latest click -> CPU decision wall
Entangler latest click -> hardware done timestamp
Entangler latest click -> run_mu() return wall
```

All values are in machine units. With the current `ref_period = 1 ns`, `1 mu`
is approximately `1 ns`.

## Measured Results

### Baseline Timing

The baseline uses:

```text
pulse_offset_us = 2.0
pulse_width_us = 2.0
cpu_gate_width_us = 10.0
entangler_cycle_length_us = 7.0
entangler_gate_pre_us = 1.0
entangler_gate_post_us = 2.0
```

Measured result:

```text
CPU branch:
  matches: 25 / 25
  latest click -> CPU decision wall: mean 1061 mu

Entangler core:
  successes: 25 / 25
  latest TTL click -> entangler done timestamp: mean 4928 mu
  latest TTL click -> run return wall: mean 6087 mu
```

Comparison:

```text
Entangler hardware done - CPU decision: +3866 mu, about 3.87 us slower
Entangler run return - CPU decision:   +5026 mu, about 5.03 us slower
```

The entangler is slower in this baseline because the core reports success at the
cycle endpoint. The click occurs near `2.07 us`, while the cycle ends near
`7 us`.

### Tight Entangler Cycle

The tight-cycle condition uses:

```text
pulse_offset_us = 1.0
pulse_width_us = 0.2
cpu_gate_width_us = 10.0
entangler_cycle_length_us = 1.6
entangler_gate_pre_us = 0.2
entangler_gate_post_us = 0.1
```

Measured result:

```text
CPU branch:
  matches: 25 / 25
  latest click -> CPU decision wall: mean 1054 mu

Entangler core:
  successes: 25 / 25
  latest TTL click -> entangler done timestamp: mean 528 mu
  latest TTL click -> run return wall: mean 1694 mu
```

Comparison:

```text
Entangler hardware done - CPU decision: -526 mu, about 0.53 us faster
Entangler run return - CPU decision:   +639 mu, about 0.64 us slower
```

This shows that the entangler hardware event can be faster when the cycle is
tight, but returning the result to Python through `run_mu()` is still slower than
the simple CPU timestamp branch.

### Fast Hardware-Done Condition

The fastest successful condition tested so far uses:

```text
pulse_offset_us = 1.0
pulse_width_us = 0.2
cpu_gate_width_us = 10.0
entangler_cycle_length_us = 1.32
entangler_gate_pre_us = 0.2
entangler_gate_post_us = 0.1
```

Measured result:

```text
CPU branch:
  matches: 25 / 25
  latest click -> CPU decision wall: mean 1065 mu

Entangler core:
  successes: 25 / 25
  latest TTL click -> entangler done timestamp: mean 247 mu
  latest TTL click -> run return wall: mean 1439 mu
```

Comparison:

```text
Entangler hardware done - CPU decision: -817 mu, about 0.82 us faster
Entangler run return - CPU decision:   +373 mu, about 0.37 us slower
```

This is the strongest case measured for the current local loopback setup. The
hardware success event is faster, but Python still sees the result later than the
CPU branch.

## Cycle-Length Sweep

The following sweep used:

```text
pulse_offset_us = 1.0
pulse_width_us = 0.2
cpu_gate_width_us = 10.0
entangler_gate_pre_us = 0.2
entangler_gate_post_us = 0.1
```

Only `entangler_cycle_length_us` was changed.

```text
cycle_us  successes  done_after_click_mu  done_minus_cpu_mu  return_minus_cpu_mu
1.32      20 / 20    247                  -807               +374
1.40      20 / 20    328                  -735               +434
1.60      20 / 20    528                  -528               +672
2.00      20 / 20    928                  -136               +1036
3.00      20 / 20    1928                 +866               +2035
5.00      20 / 20    3928                 +2872              +4045
7.00      20 / 20    5928                 +4880              +6056
```

The entangler hardware success event is faster than the CPU decision when the
cycle is below roughly `2 us` for this two-click loopback test. Once the cycle is
several microseconds long, the CPU timestamp branch wins the one-shot comparison.

## Relevance To The Current Experiment Code

The current experiment workflow does more than decide whether a photon pattern
matched. It uses the actual photon timestamp to schedule later work:

```text
SPCM click time -> microwave mapping at click_time + offset
```

The follow-up branch also includes Python/ARTIQ-controlled DDS updates, TTL
switching, FORT ramping, blow-away, atom parity readout, and dataset updates.

The current entangler core does not replace that whole dynamic branch. It can
match a pattern in hardware and return success/timeout to Python. It does not
currently implement:

```text
on SPCM0-only match:
    schedule the microwave sequence at click_time + offset

on SPCM1-only match:
    schedule a different microwave sequence at click_time + offset
```

The current driver path is:

```text
entangler.run_mu(...)
Python resumes after success/timeout
Python branches and schedules follow-up actions
```

For the current no-master/satellite workflow, this is not a faster replacement
for the existing CPU timestamp branch. The CPU branch already uses RTIO hardware
to timestamp photon edges, and the CPU decision time is about `1 us` after the
latest click.

## Conclusion

Replacing the current local timestamp/branch code with the current entangler core
is not recommended if the goal is a faster Python-visible response.

The entangler core is faster only at the hardware-success-event level when its
cycle is made short enough. If Python must wait for `run_mu()` before doing the
microwave/FORT/readout sequence, the handoff overhead makes it slower than the
current CPU timestamp branch in the tested local scenarios.

The entangler core would become useful for this workflow if the time-critical
response moved into gateware. For example:

```text
SPCM0-only match -> emit a hardware response TTL
SPCM1-only match -> emit a different hardware response TTL
pattern match -> start a gateware response sequencer
```

In that design, Python can observe the result later while the time-critical
response happens in hardware. Without that gateware response path, replacing the
current code with the entangler core is unlikely to improve the experiment.

