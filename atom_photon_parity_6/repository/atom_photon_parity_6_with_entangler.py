"""Run parity experiment 6 from the entangler-core runtime environment.

The full QN parity-6 physics sequence is still the source of truth. This entry
point requires the atom-photon entangler device DB, verifies that the custom
driver is available, and leaves the core in passthrough mode before running the
software sequence. Use the timing/loopback experiments in this repository to
exercise the gateware-owned fast loop directly.
"""

from __future__ import annotations

from artiq.experiment import EnvExperiment, kernel

from parity_6_common import Parity6Base


class AtomPhotonParity6WithEntanglerCore(Parity6Base, EnvExperiment):
    """Full parity-6 sequence in the entangler-capable ARTIQ environment."""

    def build(self):
        self.setattr_device("entangler")
        self.build_parity_6()

    @kernel
    def disable_entangler_passthrough(self):
        self.entangler.clear()
        self.entangler.configure(0)

    def run(self):
        from subroutines.experiment_functions import atom_photon_parity_6_experiment

        self.disable_entangler_passthrough()
        self.initialize_hardware()
        self.disable_entangler_passthrough()
        atom_photon_parity_6_experiment(self)
