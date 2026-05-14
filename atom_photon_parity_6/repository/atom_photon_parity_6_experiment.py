"""Run the full qn_artiq_routines atom_photon_parity_6_experiment.

This is a thin ARTIQ wrapper around the parity-6 subroutine in
``repos/qn_artiq_routines/subroutines/experiment_functions.py``. It gives the
custom gateware environment a normal dashboard/artiq_run entry point while
keeping the physics sequence in the QN routines repository.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from artiq.experiment import *


def _workspace_root() -> Path:
    here = Path(__file__).resolve()
    return here.parents[4]


def _qn_root() -> Path:
    override = os.environ.get("QN_ARTIQ_ROUTINES_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return _workspace_root() / "repos" / "qn_artiq_routines"


def _ensure_qn_paths() -> Path:
    qn_root = _qn_root()
    if not qn_root.exists():
        raise FileNotFoundError(
            f"Could not find qn_artiq_routines at {qn_root}. "
            "Set QN_ARTIQ_ROUTINES_PATH if it lives somewhere else."
        )
    for path in [qn_root, qn_root.parent]:
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    _ensure_backslash_config_aliases(qn_root)
    return qn_root


def _ensure_backslash_config_aliases(qn_root: Path) -> None:
    """Support QN helper code that still builds Windows-style config paths."""

    config_source = qn_root / "utilities" / "config"
    config_alias = Path.cwd() / "repository\\qn_artiq_routines\\utilities\\config\\"
    config_alias.mkdir(parents=True, exist_ok=True)

    for source_dir in config_source.iterdir():
        if not source_dir.is_dir():
            continue
        target_dir = config_alias / source_dir.name
        target_dir.mkdir(parents=True, exist_ok=True)
        for source_file in source_dir.iterdir():
            if source_file.is_file():
                shutil.copy2(source_file, target_dir / source_file.name)


class AtomPhotonParity6Experiment(EnvExperiment):
    """Run the lab parity-6 sequence with GUI knobs for common overrides."""

    def build(self):
        _ensure_qn_paths()

        # Keep this before BaseExperiment: BaseExperiment reads which_node in
        # its constructor.
        self.setattr_argument(
            "which_node",
            EnumerationValue(["alice", "bob", "two_nodes"], default="alice"),
            "Parity 6",
        )
        self.set_dataset("which_node", self.which_node, broadcast=True, persist=True)

        from utilities.BaseExperiment import BaseExperiment

        self.base = BaseExperiment(experiment=self)
        self.base.build()

        self.setattr_argument(
            "n_measurements",
            NumberValue(int(self.n_measurements), ndecimals=0, step=1),
            "Parity 6",
        )
        self.setattr_argument(
            "target_780_HWP",
            NumberValue(float(self.target_780_HWP), ndecimals=3, step=0.1),
            "Parity 6",
        )
        self.setattr_argument(
            "target_780_QWP",
            NumberValue(float(self.target_780_QWP), ndecimals=3, step=0.1),
            "Parity 6",
        )
        self.setattr_argument(
            "n_excitation_attempts",
            NumberValue(int(self.n_excitation_attempts), ndecimals=0, step=1),
            "Parity 6",
        )
        self.setattr_argument(
            "enable_laser_feedback",
            BooleanValue(bool(self.enable_laser_feedback)),
            "Parity 6",
        )
        self.setattr_argument(
            "t_MW_RF_pulse",
            NumberValue(float(self.t_MW_RF_pulse), unit="us"),
            "Parity 6",
        )

        self.base.set_datasets_from_gui_args()

    def prepare(self):
        self.base.prepare()

    @kernel
    def initialize_hardware(self):
        self.base.initialize_hardware()

    def run(self):
        from subroutines.experiment_functions import atom_photon_parity_6_experiment

        self.initialize_hardware()
        atom_photon_parity_6_experiment(self)
