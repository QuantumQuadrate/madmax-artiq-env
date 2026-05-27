"""Compatibility entry point for the parity-6 dashboard experiment."""

import atom_photon_parity_6_no_entangler as _no_entangler


class AtomPhotonParity6Experiment(_no_entangler.AtomPhotonParity6NoEntangler):
    """Backward-compatible class name for existing scripts."""
