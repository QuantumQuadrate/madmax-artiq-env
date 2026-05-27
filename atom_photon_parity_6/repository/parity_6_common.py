"""Shared dashboard setup for the parity-6 runtime experiments."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from artiq.experiment import *


def _runtime_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _workspace_root() -> Path:
    return _runtime_root().parents[2]


def _qn_root() -> Path:
    override = os.environ.get("QN_ARTIQ_ROUTINES_PATH")
    if override:
        return Path(override).expanduser().resolve()

    bundled = _runtime_root() / "support" / "qn_artiq_routines"
    if bundled.exists():
        return bundled

    return _workspace_root() / "repos" / "qn_artiq_routines"


def ensure_qn_paths() -> Path:
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
    return qn_root


class Parity6Base:
    """Mixin that builds the QN BaseExperiment and common parity-6 arguments."""

    def build_parity_6(self):
        ensure_qn_paths()

        # Keep this before BaseExperiment: BaseExperiment reads which_node in
        # its constructor.
        self.setattr_argument(
            "which_node",
            EnumerationValue(["alice", "bob", "two_nodes"], default="alice"),
            "Parity 6",
        )
        try:
            self.set_dataset("which_node", self.which_node, broadcast=True, persist=True)
        except AttributeError:
            # ARTIQ's repository scanner uses ExamineDatasetMgr, which can read
            # datasets but cannot persist updates while discovering experiments.
            pass

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
