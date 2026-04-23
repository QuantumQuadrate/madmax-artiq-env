There are 2 ways to create the env

## UV (recomended)
Using UV a fast package manager that is also chatGPT friendly. This method you might need to install some debian dependencies yourselve, in the case that you are using the VM ware it is already installed. 

``` bash
uv lock --upgrade
uv sync
source .venv/bin/activate
```

```bash
sudo apt install llvm lld
```


## Nix (not supported)
This is a more reproducable way to manage enviornment. however it is not really user friendly. Moreover it is not ChatGPT friendly and the error messages are not helpful. Lastly 

## Entangler diagnostics and current findings

The current one-DIO entangler setup has been tested with these loopbacks:

```text
ttl5 output -> ttl1 input    entangler output 1 -> entangler input 1
ttl4 output -> ttl3 input    entangler output 0 -> entangler input 3
```

Before running TTL loopback or entangler experiments from ARTIQ, make sure the
dashboard/moninj input override is not forcing the relevant TTL inputs. A forced
input can make a line appear stuck high and can hide real loopback behavior.

### Runtime settings must match the flashed bitstream

The flashed entangler bitstream currently behaves as though it was built with
two allowed herald patterns:

```toml
NUM_PATTERNS_ALLOWED = 2
```

With four entangler inputs, this puts the pattern-enable field at bit 8:

```text
pattern_enable_shift = NUM_PATTERNS_ALLOWED * NUM_ENTANGLER_INPUT_SIGNALS
                     = 2 * 4
                     = 8
```

If the runtime Python settings say `NUM_PATTERNS_ALLOWED = 4`, the driver writes
the enable bit at bit 16 instead. In that mismatch state, the entangler input
timestamp registers can still show valid clicks, but the pattern matcher never
asserts success and the run returns timeout reason `0x3fff`.

If the gateware is rebuilt with a different `NUM_PATTERNS_ALLOWED`, update
`entangler/settings.toml` to match the flashed bitstream before starting ARTIQ.

### CPU vs entangler benchmark

Use `entangler/repository/entangler_match_vs_cpu_branch.py` to compare the CPU
TTL timestamp branch against the entangler-core pattern match.

From the repository root:

```bash
SETTINGS_FILE_FOR_DYNACONF="$PWD/entangler/settings.toml" PYTHONNOUSERSITE=1 \
timeout 240s entangler/.venv/bin/python -I -m artiq.frontend.artiq_run \
  --device-db entangler/device_db.py \
  --dataset-db entangler/dataset_db.pyon \
  -c EntanglerMatchVsCpuBranchTiming \
  entangler/repository/entangler_match_vs_cpu_branch.py \
  repetitions=25
```

The benchmark has these timing modes:

```text
test_condition = baseline                 # use the normal timing arguments
test_condition = tight_entangler_cycle    # force a short cycle that ends soon after the input gate
test_condition = fast_hardware_done       # shortest tested successful cycle for this loopback setup
test_condition = custom                   # use the timing arguments as supplied
```

The default benchmark arguments are set for the loopbacks above:

```text
cpu_output_names = ttl5,ttl4
input_names = ttl1,ttl3
entangler_output_indices = 1,0
entangler_input_indices = 1,3
expected pattern = 0b1010
```

#### Baseline result

With the current settings and bitstream, a 25-shot baseline run produced:

```text
CPU branch:
  matches: 25 / 25
  ttl5 -> ttl1 latency: 145-147 mu
  ttl4 -> ttl3 latency: 145-146 mu
  latest click -> CPU decision wall: mean 1061 mu

Entangler core:
  successes: 25 / 25
  timeouts: 0
  reason values: [1]
  input timestamps: about 2071-2072 mu
  latest TTL click -> entangler done timestamp: mean 4928 mu
  latest TTL click -> run return wall: mean 6087 mu
```

With `ref_period = 1 ns`, the measured comparison was:

```text
Entangler done timestamp - CPU decision: mean +3866 mu, about +3.87 us
Entangler run return wall - CPU decision: mean +5026 mu, about +5.03 us
```

For this specific benchmark configuration, the entangler reports success later
than the CPU branch. This is mostly set by the configured entangler cycle timing:
the click occurs near 2.07 us and the cycle length is about 7 us, so success is
reported at the cycle endpoint. Reducing the entangler cycle length and moving
the input/output windows earlier is the main tuning knob if a faster hardware
response is needed.

This baseline does not mean the entangler core is slower in principle. It means
the benchmark is a very small one-shot decision where the CPU reads two hardware
TTL timestamps and checks that both arrived. The entangler core is intended for
deterministic gateware-controlled repeated attempts, fixed output/input windows,
pattern matching, timeout handling, and master/slave coordination. In other
words, it removes the CPU from the experiment timing hot path; it is not
automatically faster than the CPU for every tiny one-shot timestamp comparison.

#### Tight-cycle result

The benchmark also includes a condition that makes the entangler cycle end soon
after the expected clicks:

```bash
SETTINGS_FILE_FOR_DYNACONF="$PWD/entangler/settings.toml" PYTHONNOUSERSITE=1 \
timeout 240s entangler/.venv/bin/python -I -m artiq.frontend.artiq_run \
  --device-db entangler/device_db.py \
  --dataset-db entangler/dataset_db.pyon \
  -c EntanglerMatchVsCpuBranchTiming \
  entangler/repository/entangler_match_vs_cpu_branch.py \
  repetitions=25 \
  'test_condition="tight_entangler_cycle"'
```

This condition uses:

```text
pulse_offset_us = 1.0
pulse_width_us = 0.2
cpu_gate_width_us = 10.0
entangler_cycle_length_us = 1.6
entangler_gate_pre_us = 0.2
entangler_gate_post_us = 0.1
```

A 25-shot run produced:

```text
CPU branch:
  matches: 25 / 25
  latest click -> CPU decision wall: mean 1054 mu

Entangler core:
  successes: 25 / 25
  timeouts: 0
  input timestamps: about 1071-1072 mu
  latest TTL click -> entangler done timestamp: mean 528 mu
  latest TTL click -> run return wall: mean 1694 mu
```

With `ref_period = 1 ns`, the tuned comparison was:

```text
Entangler done timestamp - CPU decision: mean -526 mu, about 0.53 us faster
Entangler run return wall - CPU decision: mean +639 mu, about 0.64 us slower
```

This is the useful distinction: the hardware success event can be faster than
the CPU decision when the entangler cycle is tight, but returning that result to
the CPU through `run_mu()` still has RTIO/driver overhead. If the next action is
kept in gateware, the entangler done timestamp is the relevant number. If Python
must branch after `run_mu()` returns, use the run-return wall number.

#### Previous fast hardware-done result

The fastest broad-pulse condition tested before narrowing the timing window was:

```bash
SETTINGS_FILE_FOR_DYNACONF="$PWD/entangler/settings.toml" PYTHONNOUSERSITE=1 \
timeout 240s entangler/.venv/bin/python -I -m artiq.frontend.artiq_run \
  --device-db entangler/device_db.py \
  --dataset-db entangler/dataset_db.pyon \
  -c EntanglerMatchVsCpuBranchTiming \
  entangler/repository/entangler_match_vs_cpu_branch.py \
  repetitions=25 \
  'test_condition="fast_hardware_done"'
```

This condition uses:

```text
pulse_offset_us = 1.0
pulse_width_us = 0.2
cpu_gate_width_us = 10.0
entangler_cycle_length_us = 1.32
entangler_gate_pre_us = 0.2
entangler_gate_post_us = 0.1
```

A 25-shot run produced:

```text
CPU branch:
  matches: 25 / 25
  latest click -> CPU decision wall: mean 1065 mu

Entangler core:
  successes: 25 / 25
  timeouts: 0
  latest TTL click -> entangler done timestamp: mean 247 mu
  latest TTL click -> run return wall: mean 1439 mu
```

With `ref_period = 1 ns`, the comparison was:

```text
Entangler done timestamp - CPU decision: mean -817 mu, about 0.82 us faster
Entangler run return wall - CPU decision: mean +373 mu, about 0.37 us slower
```

An even earlier-click custom condition was also tested:

```text
pulse_offset_us = 0.5
pulse_width_us = 0.1
entangler_cycle_length_us = 1.0
entangler_gate_pre_us = 0.1
entangler_gate_post_us = 0.1
```

It succeeded 20/20 and produced:

```text
Entangler done timestamp - CPU decision: mean -638 mu, about 0.64 us faster
Entangler run return wall - CPU decision: mean +538 mu, about 0.54 us slower
```

The `fast_hardware_done` condition is faster because the cycle endpoint is only
about 247 ns after the click; the 1.0 us cycle with an earlier click leaves about
423 ns between click and cycle endpoint.

#### Narrow 200 ns and 40 ns window result

A follow-up test narrowed the output pulse and input gate, then compared cycle
endpoints near `200 ns` and `40 ns` after the latest observed click:

```bash
SETTINGS_FILE_FOR_DYNACONF="$PWD/entangler/settings.toml" PYTHONNOUSERSITE=1 \
timeout 240s entangler/.venv/bin/python -I -m artiq.frontend.artiq_run \
  --device-db entangler/device_db.py \
  --dataset-db entangler/dataset_db.pyon \
  -c EntanglerMatchVsCpuBranchTiming \
  entangler/repository/entangler_match_vs_cpu_branch.py \
  repetitions=20 \
  'variant="both"' \
  'test_condition="custom"' \
  pulse_offset_us=1.0 \
  pulse_width_us=0.04 \
  cpu_gate_width_us=10.0 \
  entangler_gate_pre_us=0.10 \
  entangler_gate_post_us=0.06
```

The `~200 ns` run used `entangler_cycle_length_us=1.276`. The `40 ns` run used
`entangler_cycle_length_us=1.104`.

```text
target done window  successes  CPU decision  HW done  run return
~200 ns             20 / 20    1077 mu       207 mu   1387 mu
40 ns               20 / 20    1070 mu       40 mu    1210 mu
```

Compared with the CPU decision:

```text
target done window  done_minus_cpu_mu  return_minus_cpu_mu
~200 ns             -869               +310
40 ns               -1030              +140
```

The `40 ns` cycle window is faster. It moves the hardware success event about
`167 ns` earlier than the `~200 ns` case, and it also reduces the `run_mu()`
return time. The Python-visible return is still slower than the direct CPU
timestamp branch because the driver/RTIO handoff remains in the path.

The matching gateware simulation also succeeded for literal `200 ns` and `40 ns`
cycle lengths; the `40 ns` simulated cycle reached `done_stb` first. The stock
entangler-core tests passed with `3 passed`, aside from the existing unknown
`slow` pytest mark warning.

#### Cycle-length sweep

Keeping the pulse near 1.0 us and using `pulse_width_us=0.2`,
`entangler_gate_pre_us=0.2`, and `entangler_gate_post_us=0.1`, the entangler
hardware done time tracks the cycle endpoint:

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

For this two-click loopback benchmark, the entangler hardware success event is
faster than the CPU decision when the cycle is below roughly 2 us. Once the
cycle is several microseconds long, the CPU wins this simple one-shot comparison.

Making the cycle smaller helps only while the real click and gate window still
fit before the cycle endpoint. The endpoint is quantized to the `8 ns` coarse
clock, the input gate must close before the cycle ends, and the narrow-window
loopback clicks landed about `72-74 ns` after the entangler pulse offset. Smaller
cycles can therefore improve the hardware timestamp down to a practical limit,
but they do not remove the `run_mu()` return overhead. For a true experiment
speedup, the next time-critical action still needs to happen in gateware.

#### Can the entangler trigger work without waiting for the CPU?

Not as a Python interrupt in the current ARTIQ kernel model. The current driver
uses `run_mu()`, which blocks until the entangler emits an RTIO input event with
success or timeout. That is interrupt-like at the RTIO/event level, but Python
kernel code still resumes only when `run_mu()` returns. The timestamp can be
ignored if only the success reason is needed, but the CPU is still in the path
for any Python-side branch.

To do work without waiting for the CPU, the work must live in gateware. Practical
options are:

```text
1. Add a success/done output from the entangler core and wire it to a TTL or
   downstream FPGA logic.
2. Add a small gateware FSM that starts a programmed action on pattern match or
   cycle success.
3. Add a register-programmable "success response" sequencer so the core emits
   a TTL pulse after a match/cycle success without returning to Python.
4. Use the current core for deterministic repeated attempts, and let Python only
   observe the final success/timeout event.
```

The existing core already performs the pattern matching and stops on success.
What it does not currently provide is a general "on match, immediately execute
an arbitrary action" engine. Adding that would be a gateware feature, not a
Python experiment change.

The benchmark publishes datasets under:

```text
cpu_vs_entangler_match/cpu_branch/...
cpu_vs_entangler_match/entangler_core/...
cpu_vs_entangler_match/comparison/...
```
