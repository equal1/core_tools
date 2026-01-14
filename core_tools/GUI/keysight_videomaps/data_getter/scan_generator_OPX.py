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
        raw_data = self.pulse_lib.opx.run()
        return {name: data for name, data in zip(self.data_channels, raw_data)}

    def get_raw(self):
        """Override base get_raw to skip Python-side bias-T correction.

        The OPX returns data already in the correct order, so we don't need
        to apply the bias-T reordering that the base class does.
        """
        raw_data = self.pulse_lib.opx.run()
        return tuple(raw_data)

    def close(self):  # pragma: no cover - hardware interaction
        self.pulse_lib.opx.close()

    def stop(self):  # pragma: no cover - matches legacy behaviour
        """Override base stop to avoid closing the OPX session on mode switches."""
        return


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

    def _resolve_iq_mode(self, iq_mode: str | None = None) -> list[str]:
        """Return the OPX channel suffixes for the requested IQ mode."""

        mode = iq_mode if iq_mode is not None else self.iq_mode
        return self._iq_mode_channels.get(mode, ["_I"])

    def _build_channel_map(self, channels: list[str]):
        """Create a channel map without touching the hardware."""

        channel_map = {
            f"ch{i + 1}": (f"ch{i + 1}", lambda x: x, "mV")
            for i in range(len(channels))
        }
        self._channel_map = channel_map
        return channel_map

    def preview_channel_map(self, iq_mode: str | None):
        """Generate a channel map for UI updates without accessing the OPX driver."""

        channels = self._resolve_iq_mode(iq_mode)
        return self._build_channel_map(channels)

    def _setup_channels(self):
        channels = self._resolve_iq_mode()
        self.pulse_lib.opx.channels = channels
        self._build_channel_map(channels)
        return list(self._channel_map.keys())

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
        self.pulse_lib.opx.sweep_gates(
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
        self.pulse_lib.opx.sweep_gates(
            m_param,
            config.names,
            config.setpoints,
            config.t_measure,
            500e6,
            config.biasT_corr,
            config.voltages2,
        )
        return m_param
