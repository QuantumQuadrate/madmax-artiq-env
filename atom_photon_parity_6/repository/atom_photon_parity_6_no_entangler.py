"""Run parity experiment 6 using the original QN software timing path."""

from __future__ import annotations

from artiq.experiment import EnvExperiment, kernel

from parity_6_common import Parity6Base


class AtomPhotonParity6NoEntangler(Parity6Base, EnvExperiment):
    """Full parity-6 sequence without using the atom-photon entangler core."""

    def build(self):
        self.build_parity_6()

    @kernel
    def disable_entangler_passthrough_if_present(self):
        # This class intentionally does not require the entangler device. The
        # entangler-aware sibling disables it explicitly when that device exists.
        pass

    def run(self):
        from subroutines.experiment_functions import atom_photon_parity_6_experiment

        self.initialize_hardware()
        self.disable_entangler_passthrough_if_present()
        atom_photon_parity_6_experiment(self)
