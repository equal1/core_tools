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
        frames = self._collect_frames()

        flattened: dict[str, np.ndarray] = {}
        for name, arr in frames.items():
            if self.config.biasT_corr:
                flattened[name] = self._encode_bias_t(arr)
            else:
                flattened[name] = arr.reshape(-1)

        return flattened

    def _collect_frames(self) -> dict[str, np.ndarray]:
        raw_data = self.pulse_lib.opx.opx_run()
        shape = self.config.shape
        size = int(np.prod(shape))

        frames: dict[str, np.ndarray] = {}
        for name, data in zip(self.data_channels, raw_data):
            arr = np.asarray(data)
            if arr.size != size:
                raise ValueError(
                    "Received data size %s does not match expected scan size %s"
                    % (arr.size, size)
                )

            arr = self._reshape_to_scan(arr, shape)
            frames[name] = arr

        return frames

    def get_raw(self):
        frames = self._collect_frames()

        data_out = []
        for ch, func, _ in self.config.channel_map.values():
            ch_data = frames[ch]
            data_out.append(func(ch_data))

        return tuple(data_out)

    @staticmethod
    def _reshape_to_scan(arr: np.ndarray, target_shape: tuple[int, ...]) -> np.ndarray:
        """Ensure array matches the scan shape and orientation."""

        if arr.ndim == len(target_shape) and arr.shape == target_shape:
            return np.array(arr, copy=True)

        if arr.ndim == len(target_shape) and arr.shape[::-1] == target_shape:
            axes = tuple(reversed(range(arr.ndim)))
            return np.array(arr.transpose(axes), copy=True)

        reshaped = np.array(arr, copy=True).reshape(target_shape)
        return reshaped

    @staticmethod
    def _encode_bias_t(arr: np.ndarray) -> np.ndarray:
        """Re-create the bias-T serpentine ordering expected by the base class."""

        if arr.ndim == 1:
            n_even = (arr.size + 1) // 2
            encoded = np.empty_like(arr)
            encoded[::2] = arr[:n_even]
            if arr.size > 1:
                encoded[1::2] = arr[n_even:][::-1]
            return encoded

        if arr.ndim == 2:
            rows = arr.shape[0]
            encoded = np.empty_like(arr)
            n_even = (rows + 1) // 2
            encoded[::2] = arr[:n_even]
            if rows > 1:
                encoded[1::2] = arr[n_even:][::-1]
            return encoded.reshape(-1)

        return arr.reshape(-1)

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
