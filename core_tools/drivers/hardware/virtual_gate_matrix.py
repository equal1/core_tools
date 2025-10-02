import logging

import numpy as np

logger = logging.getLogger(__name__)


class VirtualGateMatrixView:
    """
    Data to convert real gate voltages to virtual gate voltages and v.v.

    Args:
        name (str): name of the matrix
        real_gates (list[str]): names of real gates
        virtual_gates (list[str]): names of virtual gates
        r2v_matrix (2D array-like): matrix to convert voltages of real gates to voltages of virtual gates.
    """

    def __init__(self, name, real_gates, virtual_gates, r2v_matrix, indices):
        self.name = name
        self._real_gates = real_gates
        self._virtual_gates = virtual_gates
        self._r2v_matrix = r2v_matrix
        self._indices = indices

    @property
    def real_gates(self):
        """
        Names of real gates
        """
        return self._real_gates

    @property
    def virtual_gate_names(self):
        """
        Names of virtual gates
        """
        return self._persistent_object.virtual_gate_names

    @property
    def normalization(self):
        return self._normalization

    @property
    def virtual_gate_matrix(self):
        return self._norm_r2v_matrix

    @property
    def virtual_gate_matrix_no_norm(self):
        return self._r2v_matrix

    @property
    def matrix(self):
        # read-only view of matrix
        matrix = self._r2v_matrix[:]
        matrix.setflags(write=False)
        return matrix

    def _set_matrix(self, value, *, persist: bool) -> None:
        value = np.asarray(value)
        if value.shape != self._r2v_matrix.shape:
            raise ValueError(
                f"Matrix shape {value.shape} does not match current shape {self._r2v_matrix.shape}."
            )

        self._r2v_matrix[:] = value
        self._v2r_matrix[:] = np.linalg.inv(self._r2v_matrix)
        self._calc_normalized()

        if persist:
            try:
                self._persistent_object.save()
            except ConnectionError as exc:
                logger.debug("Skipping virtual-gate persistence: %s", exc)

    @matrix.setter
    def matrix(self, value):
        self._set_matrix(value, persist=True)

    def update_matrix(self, value, *, persist: bool = False) -> None:
        """Update the virtual gate matrix, optionally skipping persistence."""
        self._set_matrix(value, persist=persist)

    @matrix.setter
    def matrix(self, value):
        self._r2v_matrix[:] = value
        self._v2r_matrix[:] = np.linalg.inv(self._r2v_matrix)
        self._calc_normalized()
        self._persistent_object.save()

    @property
    def gates(self):
        return self.real_gate_names

    @property
    def v_gates(self):
        return self.virtual_gate_names

    def get_element(self, i, j, v2r=True):
        if v2r:
            return self._v2r_matrix[i, j]
        else:
            return self._r2v_matrix[i, j]

    def set_element(self, i, j, value, v2r=True):
        if v2r:
            self._v2r_matrix[i, j] = value
            self._r2v_matrix[:] = np.linalg.inv(self._v2r_matrix)
        else:
            self._r2v_matrix[i, j] = value
            self._v2r_matrix[:] = np.linalg.inv(self._r2v_matrix)

        self._calc_normalized()
        self._persistent_object.save()

    def normalize(self):
        if self._normalization:
            self._r2v_matrix[:] = self._norm_r2v_matrix
            self._v2r_matrix[:] = np.linalg.inv(self._r2v_matrix)
            self._persistent_object.save()

    def reverse_normalize(self):
        if self._normalization:
            # divide columns of v2r by diagonal value
            self._v2r_matrix[:] = self._v2r_matrix / np.diag(self._v2r_matrix)
            self._r2v_matrix[:] = np.linalg.inv(self._v2r_matrix)
            self._persistent_object.save()

    def _calc_normalized(self):
        no_norm = self._r2v_matrix

        if self._normalization:
            # divide rows by diagonal value
            norm = no_norm / np.diag(no_norm)[:, None]
        else:
            norm = no_norm

        self._norm_r2v_matrix[:] = norm

    def get_view(self, available_gates):
        gate_indices = []
        real_gate_names = []
        virtual_gate_names = []

        for i, name in enumerate(self.real_gate_names):
            if name in available_gates:
                gate_indices.append(i)
                real_gate_names.append(name)
                virtual_gate_names.append(self.virtual_gate_names[i])

        return VirtualGateMatrixView(
            self.name,
            real_gate_names,
            virtual_gate_names,
            self._norm_r2v_matrix,
            gate_indices,
        )
