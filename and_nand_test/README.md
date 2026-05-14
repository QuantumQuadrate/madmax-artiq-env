# and_nand_test ARTIQ Runtime

Runtime files for the `feature/and-nand-test` entangler-core branch.

Expected DIO wiring:

- `dio0`, `dio1`: logic inputs for AND/NAND.
- `dio4`: AND output.
- `dio5`: NAND output.
- `dio6` looped back to `dio2`: timer bit 0 timestamp input.
- `dio7` looped back to `dio3`: timer bit 1 timestamp input.

Run the experiments in order: smoke, loopback, timing scan, stress test, then benchmark. Keep this runtime environment matched to the same local entangler-core checkout used by `madmax-artiq-zynq/flake.nix`.
