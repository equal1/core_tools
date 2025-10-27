from __future__ import annotations

import logging
import math
from collections.abc import Callable, Sequence

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets

from ..qt_util import qt_log_exception
from ..script_runner.script_runner_main import ScriptRunner
from .virt_gate_matrix_window import Ui_MainWindow

logger = logging.getLogger(__name__)

# add near your imports


class AutoStretchTable(QtWidgets.QTableWidget):
    def __init__(self, *args, min_col=70, row_h=32, **kwargs):
        super().__init__(*args, **kwargs)
        self._min_col = min_col

        # no "adjust to contents" flicker
        self.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustIgnored)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.verticalHeader().setDefaultSectionSize(row_h)

        # do an initial pass after the first layout
        QtCore.QTimer.singleShot(0, self._stretch_now)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._stretch_now()

    def _stretch_now(self):
        cols = self.columnCount()
        if cols <= 0:
            return
        # available pixels in the viewport (minus a scrollbar if visible)
        avail = self.viewport().width()
        if self.verticalScrollBar().isVisible():
            avail -= self.verticalScrollBar().width()
        w = max(self._min_col, int(avail / cols))
        for c in range(cols):
            self.setColumnWidth(c, w)


class AutoFitDoubleSpinBox(QtWidgets.QDoubleSpinBox):
    """QDoubleSpinBox that scales its font to fit the current cell size."""

    def __init__(self, parent=None, *, min_px=10, max_px=28, side_pad=6, top_pad=4):
        super().__init__(parent)
        self._min_px = min_px
        self._max_px = max_px
        self._side_pad = side_pad
        self._top_pad = top_pad
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.setFrame(False)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.lineEdit().textChanged.connect(self.refit_font)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.refit_font()

    def refit_font(self):
        # choose a representative string (current text or a template)
        txt = self.text() or "−0.000"
        cr = self.contentsRect()
        avail_w = max(0, cr.width() - self._side_pad)
        avail_h = max(0, cr.height() - self._top_pad)

        # upper bound by height; binary search the largest pixel size that fits width+height
        low = self._min_px
        high = min(self._max_px, int(avail_h * 0.85)) or self._min_px
        best = low
        while low <= high:
            mid = (low + high) // 2
            f = self.font()
            f.setPixelSize(mid)
            fm = QtGui.QFontMetrics(f)
            if fm.horizontalAdvance(txt) <= avail_w and fm.height() <= avail_h:
                best = mid
                low = mid + 1
            else:
                high = mid - 1

        f = self.font()
        f.setPixelSize(best)
        self.setFont(f)
        self.lineEdit().setFont(f)


class virt_gate_matrix_GUI(QtWidgets.QMainWindow, Ui_MainWindow):
    """Virtual-gate matrix editor with optional ScriptRunner tab."""

    def __init__(
        self,
        gates_object,
        pulse_lib,
        *,
        coloring: bool = True,
        allowed_gates: Sequence[str] | None = None,
        on_matrix_changed: Callable[[], None] | None = None,
        on_push_to_config: Callable[[], None] | None = None,
    ):
        self.gates_object = gates_object
        self.pulse_lib = pulse_lib
        self._coloring = coloring
        self._on_matrix_changed = on_matrix_changed
        self._on_push_to_config = on_push_to_config
        self.timers: list[QtCore.QTimer] = []
        self._updating = False

        if allowed_gates is None:
            self._allowed_gate_keys: set[str] | None = None
        else:
            self._allowed_gate_keys = set(allowed_gates)

        self.app = QtCore.QCoreApplication.instance()
        instance_ready = True
        if self.app is None:
            instance_ready = False
            self.app = QtWidgets.QApplication([])

        super(QtWidgets.QMainWindow, self).__init__()
        self.setupUi(self)

        hardware = self.gates_object.hardware
        for virtual_gate_set in hardware.virtual_gates:
            self._add_matrix(virtual_gate_set)

        self.script_runner = ScriptRunner(parent=self.tabWidget, embedded=True)
        script_tab_index = self.tabWidget.addTab(self.script_runner, "Scripts")
        if script_tab_index != -1:
            self.tabWidget.setCurrentIndex(script_tab_index)
            self.script_runner.setFocus(QtCore.Qt.OtherFocusReason)

        self.show()
        if not instance_ready:
            self.app.exec()

    def _intensity(self, x: float, k: float = 0.01) -> float:
        """Saturating intensity: emphasizes small |x|, then levels off."""
        return 1.0 - math.exp(-abs(x) / k)

    # ------------------------------------------------------------------
    def _select_indices(self, real_gate_names: Sequence[str]) -> list[int]:
        if self._allowed_gate_keys is None:
            return list(range(len(real_gate_names)))

        indices = [
            idx
            for idx, name in enumerate(real_gate_names)
            if name in self._allowed_gate_keys
        ]

        if not indices:
            raise RuntimeError(
                f"None of the requested gates ({sorted(self._allowed_gate_keys)}) "
                f"are present in the hardware virtual matrix."
            )

        if self._allowed_gate_keys is not None:
            actual = {real_gate_names[i] for i in indices}
            missing = self._allowed_gate_keys.difference(actual)
            if missing:
                raise RuntimeError(
                    f"Some gates are missing from the virtual matrix: {sorted(missing)}"
                )
        return indices

    # ------------------------------------------------------------------
    @qt_log_exception
    def closeEvent(self, event):
        for timer in self.timers:
            timer.stop()

    # ------------------------------------------------------------------
    def _add_matrix(self, virtual_gate_set) -> None:
        indices = self._select_indices(virtual_gate_set.real_gate_names)
        if not indices:
            return

        matrix_widget = QtWidgets.QWidget()
        grid_layout = QtWidgets.QGridLayout(matrix_widget)
        grid_layout.setSpacing(4)
        grid_layout.setContentsMargins(2, 2, 2, 2)

        table = AutoStretchTable(matrix_widget)
        table.setObjectName("virtgates")
        table.setRowCount(len(indices))
        table.setColumnCount(len(indices))
        table.setProperty("row_indices", indices)
        table.setProperty("col_indices", indices)
        font = QtGui.QFont()
        font.setPointSize(11)
        table.setFont(font)
        table.horizontalHeader().setDefaultSectionSize(60)
        table.horizontalHeader().setMinimumSectionSize(40)
        table.horizontalHeader().setMaximumSectionSize(140)
        table.verticalHeader().setDefaultSectionSize(26)
        grid_layout.addWidget(table, 0, 0, 1, 1)

        state = {"v2r": False}
        update_list: list[tuple[int, int, AutoFitDoubleSpinBox]] = []

        for col_pos, col_idx in enumerate(indices):
            header_item = QtWidgets.QTableWidgetItem()
            header_item.setText(virtual_gate_set.real_gate_names[col_idx])
            table.setHorizontalHeaderItem(col_pos, header_item)

        for row_pos, row_idx in enumerate(indices):
            header_item = QtWidgets.QTableWidgetItem()
            header_item.setText(virtual_gate_set.virtual_gate_names[row_idx])
            table.setVerticalHeaderItem(row_pos, header_item)

            for col_pos, col_idx in enumerate(indices):
                spin_box = AutoFitDoubleSpinBox()
                spin_box.setDecimals(3)
                spin_box.setSingleStep(0.001)
                spin_box.setMinimum(-5.0)
                spin_box.setMaximum(5.0)
                spin_box.setFrame(False)
                spin_box.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                spin_box.setAlignment(QtCore.Qt.AlignCenter)
                value = virtual_gate_set.get_element(row_idx, col_idx, v2r=False)
                spin_box.setValue(value)

                # Make diagonal elements read-only
                if row_idx == col_idx:
                    spin_box.setReadOnly(True)
                else:
                    spin_box.valueChanged.connect(
                        self._get_link(
                            virtual_gate_set,
                            row_idx,
                            col_idx,
                            spin_box,
                            state,
                            update_list,
                        )
                    )

                update_list.append((row_idx, col_idx, spin_box))
                table.setCellWidget(row_pos, col_pos, spin_box)
                self.set_color(spin_box, value)

        refresh = lambda: self.update_v_gates(virtual_gate_set, update_list, state)
        timer = QtCore.QTimer()
        timer.timeout.connect(refresh)
        timer.start(2000)
        self.timers.append(timer)

        control_bar = QtWidgets.QWidget()
        bar_layout = QtWidgets.QHBoxLayout(control_bar)
        bar_layout.setContentsMargins(2, 2, 2, 2)

        invert_btn = QtWidgets.QPushButton("Invert matrix")
        invert_btn.setMinimumSize(QtCore.QSize(150, 28))
        invert_btn.clicked.connect(
            lambda: self.invert(virtual_gate_set, refresh, table, state)
        )
        invert_btn.setEnabled(False)
        invert_btn.setVisible(False)
        bar_layout.addWidget(invert_btn)

        if getattr(virtual_gate_set, "normalization", False):
            normalize_btn = QtWidgets.QPushButton("Normalize")
            normalize_btn.setMinimumSize(QtCore.QSize(150, 28))
            normalize_btn.clicked.connect(
                lambda: self.normalize(virtual_gate_set, refresh)
            )
            bar_layout.addWidget(normalize_btn)

            reverse_btn = QtWidgets.QPushButton("Reverse normalize")
            reverse_btn.setMinimumSize(QtCore.QSize(150, 28))
            reverse_btn.clicked.connect(
                lambda: self.reverse_normalize(virtual_gate_set, refresh)
            )
            bar_layout.addWidget(reverse_btn)

        if self._on_push_to_config is not None:
            push_btn = QtWidgets.QPushButton("Write to OPX config")
            push_btn.setMinimumSize(QtCore.QSize(170, 28))
            push_btn.clicked.connect(self._on_push_to_config)
            bar_layout.addWidget(push_btn)

        bar_layout.addStretch(1)
        grid_layout.addWidget(control_bar, 1, 0, 1, 1)

        tab_title = virtual_gate_set.name or "Virtual gates"
        self.tabWidget.addTab(matrix_widget, tab_title)

    # ------------------------------------------------------------------
    def _get_link(self, virtual_gate_set, i, j, spin_box, state, update_list):
        return lambda: self.linked_result(
            virtual_gate_set, i, j, spin_box, state, update_list
        )

    # ------------------------------------------------------------------
    @qt_log_exception
    def normalize(self, virtual_gate_set, refresh):
        logger.info("Normalize %s", virtual_gate_set.name)
        virtual_gate_set.normalize()
        refresh()

    # ------------------------------------------------------------------
    @qt_log_exception
    def reverse_normalize(self, virtual_gate_set, refresh):
        logger.info("Reverse normalize %s", virtual_gate_set.name)
        virtual_gate_set.reverse_normalize()
        refresh()

    # ------------------------------------------------------------------
    @qt_log_exception
    def linked_result(self, virtual_gate_set, i, j, spin_box, state, update_list):
        if self._updating:
            return

        value = spin_box.value()
        r2v_matrix = np.array(virtual_gate_set.matrix, dtype=float)
        try:
            if state["v2r"]:
                v2r_matrix = np.linalg.inv(r2v_matrix)
                v2r_matrix[i, j] = value
                r2v_new = np.linalg.inv(v2r_matrix)
            else:
                r2v_new = r2v_matrix
                r2v_new[i, j] = value
        except np.linalg.LinAlgError:
            logger.warning("Virtual gate matrix became singular; reverting change.")
            current = virtual_gate_set.get_element(i, j, v2r=state["v2r"])
            spin_box.blockSignals(True)
            spin_box.setValue(current)
            spin_box.blockSignals(False)
            return

        virtual_gate_set.update_matrix(r2v_new, persist=False)
        if self._on_matrix_changed is not None:
            self._on_matrix_changed()

        refresh = lambda: self.update_v_gates(virtual_gate_set, update_list, state)
        refresh()
        self.set_color(spin_box, value)

    # ------------------------------------------------------------------
    @qt_log_exception
    def update_v_gates(self, virtual_gate_set, update_list, state):
        self._updating = True
        try:
            for i, j, spin_box in update_list:
                if spin_box.hasFocus():
                    continue
                value = virtual_gate_set.get_element(i, j, v2r=state["v2r"])
                spin_box.blockSignals(True)
                spin_box.setValue(value)
                spin_box.blockSignals(False)
                self.set_color(spin_box, value)
        finally:
            self._updating = False

    # ------------------------------------------------------------------
    def set_color(self, spin_box, value):
        if not self._coloring:
            return
        if value == 0.0:
            spin_box.setStyleSheet("background-color:rgb(255,255,255);")
            return

        # emphasize small contributions; saturate for larger
        intensity = self._intensity(value, k=0.01)  # tweak k to taste

        min_channel = 150  # deepest tint channel value
        delta = 255 - min_channel
        shade = int(255 - intensity * delta)

        if value > 0:
            # positive -> blue tint
            r = g = shade
            b = 255
        else:
            # negative -> red tint
            r = 255
            g = b = shade

        spin_box.setStyleSheet(f"background-color:rgb({r},{g},{b});")

    # ------------------------------------------------------------------
    @qt_log_exception
    def invert(self, virtual_gate_set, refresh, tableWidget, state):
        state["v2r"] = not state["v2r"]
        indices = tableWidget.property("row_indices") or []
        if state["v2r"]:
            for pos, idx in enumerate(indices):
                tableWidget.horizontalHeaderItem(pos).setText(
                    virtual_gate_set.virtual_gate_names[idx]
                )
                tableWidget.verticalHeaderItem(pos).setText(
                    virtual_gate_set.real_gate_names[idx]
                )
        else:
            for pos, idx in enumerate(indices):
                tableWidget.horizontalHeaderItem(pos).setText(
                    virtual_gate_set.real_gate_names[idx]
                )
                tableWidget.verticalHeaderItem(pos).setText(
                    virtual_gate_set.virtual_gate_names[idx]
                )
        refresh()
