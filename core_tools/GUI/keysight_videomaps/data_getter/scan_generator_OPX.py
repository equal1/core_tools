import numpy as np
from qcodes import MultiParameter

from .scan_generator_base import (
    FastScanGeneratorBase,
    FastScanParameterBase,
    ScanConfigBase,
)


class fake_digitizer(MultiParameter):
    """Dummy digitizer used when no hardware is available."""

    def __init__(self, name: str):
        super().__init__(
            name=name,
            names=("chan_1", "chan_2"),
            shapes=tuple([(20, 20)] * 2),
            labels=("chan 1", "chan 2"),
            units=("mV", "mV"),
            docstring="1D scan parameter for digitizer",
        )

    def get_raw(self):  # pragma: no cover - deterministic output
        return 0


class OPXFastScanParameter(FastScanParameterBase):
    """Fast scan parameter for the OPX based video-mode sweeps."""

    def __init__(
        self,
        scan_config: ScanConfigBase,
        pulse_lib,
        data_channels: list[str],
    ):
        self.pulse_lib = pulse_lib
        self.data_channels = data_channels
        super().__init__(scan_config)

    def recompile(self):  # pragma: no cover - nothing to recompile
        pass

    def get_channel_data(self) -> dict[str, np.ndarray]:
        raw_data = self.pulse_lib.opx.opx_run()
        return {name: data for name, data in zip(self.data_channels, raw_data)}

    def close(self):  # pragma: no cover - hardware interaction
        if hasattr(self.pulse_lib, "opx"):
            self.pulse_lib.opx.opx_close()


class FastScanGenerator(FastScanGeneratorBase):
    """Generator creating fast scan parameters for the OPX backend."""

    _iq_mode_channels = {
        "I+Q": ["_I", "_Q"],
        "I": ["_I"],
        "Q": ["_Q"],
        "Magnitude": ["_Magnitude"],
        "Mag+Phase": ["_Magnitude", "_Phase"],
        "MagdBm": ["_Mag_dBm"],
        "MagdBm+Phase": ["_Mag_dBm", "_Phase"],
        "Phase": ["_Phase"],
        # "transport": ["_Transport_DC_current"], # Disable for now
    }

    def _setup_channels(self):
        channels = self._iq_mode_channels.get(self.iq_mode, ["_I"])
        self.pulse_lib.opx.channels = channels
        channel_map = {
            f"ch{i + 1}": (f"ch{i + 1}", lambda x: x, "mV")
            for i in range(len(channels))
        }
        self._channel_map = channel_map
        return list(channel_map.keys())

    def create_1D_scan(
        self,
        gate: str,
        swing: float,
        n_pt: int,
        t_measure: float,
        pulse_gates: dict[str, float] | None = None,
        biasT_corr: bool = False,
    ) -> FastScanParameterBase:
        if pulse_gates is None:
            pulse_gates = {}

        data_channels = self._setup_channels()
        config = self.get_config1D(
            gate, swing, n_pt, t_measure, pulse_gates, biasT_corr
        )

        m_param = OPXFastScanParameter(config, self.pulse_lib, data_channels)
        self.pulse_lib.opx.opx_update_sweep(
            m_param,
            config.names,
            config.setpoints,
            config.t_measure,
            500e6,
            config.biasT_corr,
            config.voltages,
        )
        return m_param

    def create_2D_scan(
        self,
        gate1: str,
        swing1: float,
        n_pt1: int,
        gate2: str,
        swing2: float,
        n_pt2: int,
        t_measure: float,
        pulse_gates: dict[str, float] | None = None,
        biasT_corr: bool = True,
    ) -> FastScanParameterBase:
        if pulse_gates is None:
            pulse_gates = {}

        data_channels = self._setup_channels()
        config = self.get_config2D(
            gate1,
            swing1,
            n_pt1,
            gate2,
            swing2,
            n_pt2,
            t_measure,
            pulse_gates,
            biasT_corr,
        )

        m_param = OPXFastScanParameter(config, self.pulse_lib, data_channels)
        self.pulse_lib.opx.opx_update_sweep(
            m_param,
            config.names,
            config.setpoints,
            config.t_measure,
            500e6,
            config.biasT_corr,
            config.voltages2,
        )
        return m_param
