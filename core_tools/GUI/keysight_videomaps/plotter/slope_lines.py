"""
Slope line measurement tool for 2D plots.

This module provides interactive line drawing on 2D plots with automatic
slope calculation. Lines can be drawn by clicking and dragging on the plot.
The slope is displayed and can be sent to virtual gate matrices.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, List, Optional

import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class SlopeLineData:
    """Data for a single slope line."""

    line_roi: pg.LineSegmentROI
    label: pg.TextItem
    slope: float = 0.0
    # Store coordinates in plot units (mV)
    p1: tuple = (0.0, 0.0)
    p2: tuple = (0.0, 0.0)


class SlopeLinesManager:
    """
    Manages slope measurement lines on 2D plots.

    Allows drawing multiple lines on the plot and calculates their slopes.
    Slopes are displayed as labels on the lines and in a summary panel.
    """

    # Single black color for all lines
    LINE_COLOR = (0, 0, 0)  # Black

    def __init__(
        self,
        plot_widget: pg.PlotWidget,
        on_slope_changed: Optional[Callable[[List[float]], None]] = None,
        x_label: str = "x",
        y_label: str = "y",
    ):
        """
        Initialize the slope lines manager.

        Args:
            plot_widget: The pyqtgraph PlotWidget to draw lines on
            on_slope_changed: Callback when any slope changes, receives list of all slopes
            x_label: Label for x-axis (gate name)
            y_label: Label for y-axis (gate name)
        """
        self.plot_widget = plot_widget
        self.on_slope_changed = on_slope_changed
        self.x_label = x_label
        self.y_label = y_label
        self.lines: List[SlopeLineData] = []
        self._enabled = False
        self._drawing = False
        self._current_line: Optional[SlopeLineData] = None
        self._start_pos = None

        # Connect mouse events
        self._proxy_click = None
        self._proxy_move = None
        self._proxy_release = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        if value:
            self._connect_mouse_events()
        else:
            self._disconnect_mouse_events()

    def _connect_mouse_events(self):
        """Connect mouse event handlers for line drawing."""
        # Use scene events for drawing
        scene = self.plot_widget.scene()
        if scene is None:
            logger.warning("Cannot connect mouse events: scene not ready")
            return

        # Disconnect first to avoid duplicate connections
        try:
            scene.sigMouseClicked.disconnect(self._on_mouse_clicked)
        except (TypeError, RuntimeError):
            pass  # Not connected

        scene.sigMouseClicked.connect(self._on_mouse_clicked)

    def _disconnect_mouse_events(self):
        """Disconnect mouse event handlers."""
        try:
            scene = self.plot_widget.scene()
            scene.sigMouseClicked.disconnect(self._on_mouse_clicked)
        except (TypeError, RuntimeError):
            pass  # Already disconnected

    def _on_mouse_clicked(self, event):
        """Handle mouse click to start/end line drawing."""
        if not self._enabled:
            return

        # Only handle left clicks
        if event.button() != QtCore.Qt.LeftButton:
            return

        # Get position in plot coordinates
        pos = event.scenePos()
        if not self.plot_widget.sceneBoundingRect().contains(pos):
            return

        mouse_point = self.plot_widget.plotItem.vb.mapSceneToView(pos)
        x, y = mouse_point.x(), mouse_point.y()

        if not self._drawing:
            # Start drawing a new line
            self._start_drawing(x, y)
        else:
            # Finish the current line
            self._finish_drawing(x, y)

        event.accept()

    def _start_drawing(self, x: float, y: float):
        """Start drawing a new line from the given position."""
        self._drawing = True
        self._start_pos = (x, y)

        # Create line ROI with single black color
        pen = pg.mkPen(color=self.LINE_COLOR, width=2)

        # Create with both points at start position initially
        line_roi = pg.LineSegmentROI(
            positions=[(x, y), (x, y)], pen=pen, movable=True, removable=True
        )
        line_roi.setZValue(1000)  # Draw on top

        # Style the handles
        for handle in line_roi.getHandles():
            handle.pen = pg.mkPen(color=self.LINE_COLOR, width=2)

        self.plot_widget.addItem(line_roi)

        # Create label for slope display
        label = pg.TextItem(text="slope: ...", color=self.LINE_COLOR, anchor=(0.5, 1))
        label.setZValue(1001)
        self.plot_widget.addItem(label)

        # Store line data
        line_data = SlopeLineData(line_roi=line_roi, label=label, p1=(x, y), p2=(x, y))
        self._current_line = line_data

        # Connect to region changed signal for dragging
        line_roi.sigRegionChanged.connect(lambda: self._on_line_moved(line_data))
        line_roi.sigRemoveRequested.connect(lambda: self.remove_line(line_data))

        # Track mouse movement to update endpoint
        self._temp_move_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved,
            rateLimit=30,
            slot=self._on_mouse_move_drawing,
        )

    def _on_mouse_move_drawing(self, event):
        """Update line endpoint while drawing."""
        if not self._drawing or self._current_line is None:
            return

        pos = event[0]
        if not self.plot_widget.sceneBoundingRect().contains(pos):
            return

        mouse_point = self.plot_widget.plotItem.vb.mapSceneToView(pos)
        x, y = mouse_point.x(), mouse_point.y()

        # Update line endpoint
        line_roi = self._current_line.line_roi
        handles = line_roi.getHandles()
        if len(handles) >= 2:
            # Move second handle to current position
            line_roi.movePoint(handles[1], (x, y))

        self._current_line.p2 = (x, y)
        self._update_line_label(self._current_line)

    def _finish_drawing(self, x: float, y: float):
        """Finish drawing the current line."""
        if self._current_line is None:
            return

        self._drawing = False

        # Disconnect temporary move handler
        if hasattr(self, "_temp_move_proxy"):
            try:
                self._temp_move_proxy.disconnect()
            except:
                pass
            del self._temp_move_proxy

        # Update final position
        self._current_line.p2 = (x, y)
        self._update_line_label(self._current_line)

        # Add to list of lines
        self.lines.append(self._current_line)
        self._current_line = None

        # Notify callback
        self._notify_slopes_changed()

        logger.info(f"Added slope line. Total lines: {len(self.lines)}")

    def _on_line_moved(self, line_data: SlopeLineData):
        """Handle line being moved/adjusted by user."""
        line_roi = line_data.line_roi

        # Get handle positions and convert to view (data) coordinates
        handles = line_roi.getHandles()
        if len(handles) >= 2:
            p1_local = handles[0].pos()
            p2_local = handles[1].pos()

            # Map from handle local coords -> scene coords -> view (data) coords
            p1_scene = line_roi.mapToScene(p1_local)
            p2_scene = line_roi.mapToScene(p2_local)

            vb = self.plot_widget.plotItem.vb
            p1_view = vb.mapSceneToView(p1_scene)
            p2_view = vb.mapSceneToView(p2_scene)

            line_data.p1 = (p1_view.x(), p1_view.y())
            line_data.p2 = (p2_view.x(), p2_view.y())

        self._update_line_label(line_data)
        self._notify_slopes_changed()

    def _update_line_label(self, line_data: SlopeLineData):
        """Update the slope label for a line."""
        p1, p2 = line_data.p1, line_data.p2
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]

        if abs(dx) > 1e-9:
            slope = dy / dx
            line_data.slope = slope
            slope_text = f"slope: {slope:.3f}"
        else:
            line_data.slope = float("inf") if dy > 0 else float("-inf")
            slope_text = "slope: ∞"

        # Position label at midpoint of line
        mid_x = (p1[0] + p2[0]) / 2
        mid_y = (p1[1] + p2[1]) / 2

        line_data.label.setText(slope_text)
        line_data.label.setPos(mid_x, mid_y)

    def _notify_slopes_changed(self):
        """Notify callback that slopes have changed."""
        if self.on_slope_changed:
            slopes = [line.slope for line in self.lines]
            self.on_slope_changed(slopes)

    def remove_line(self, line_data: SlopeLineData):
        """Remove a specific line."""
        if line_data in self.lines:
            self.lines.remove(line_data)

        # Remove from plot
        try:
            self.plot_widget.removeItem(line_data.line_roi)
            self.plot_widget.removeItem(line_data.label)
        except Exception as e:
            logger.warning(f"Error removing line: {e}")

        self._notify_slopes_changed()
        logger.info(f"Removed slope line. Remaining: {len(self.lines)}")

    def clear_all_lines(self):
        """Remove all slope lines."""
        for line_data in self.lines.copy():
            self.remove_line(line_data)
        self.lines.clear()

        # Also clear any line being drawn
        if self._current_line is not None:
            try:
                self.plot_widget.removeItem(self._current_line.line_roi)
                self.plot_widget.removeItem(self._current_line.label)
            except:
                pass
            self._current_line = None
            self._drawing = False

    def get_slopes(self) -> List[float]:
        """Get list of all current slopes."""
        return [line.slope for line in self.lines]

    def get_slopes_summary(self) -> str:
        """Get a formatted summary of all slopes."""
        if not self.lines:
            return "No slope lines"

        lines_text = []
        for i, line in enumerate(self.lines):
            if abs(line.slope) != float("inf"):
                lines_text.append(f"Line {i + 1}: {line.slope:.4f}")
            else:
                lines_text.append(f"Line {i + 1}: ∞")
        return "\n".join(lines_text)

    def add_line_at(self, x1: float, y1: float, x2: float, y2: float) -> SlopeLineData:
        """
        Programmatically add a slope line.

        Args:
            x1, y1: Start point coordinates
            x2, y2: End point coordinates

        Returns:
            The created SlopeLineData
        """
        pen = pg.mkPen(color=self.LINE_COLOR, width=2)

        line_roi = pg.LineSegmentROI(
            positions=[(x1, y1), (x2, y2)], pen=pen, movable=True, removable=True
        )
        line_roi.setZValue(1000)
        self.plot_widget.addItem(line_roi)

        label = pg.TextItem(text="slope: ...", color=self.LINE_COLOR, anchor=(0.5, 1))
        label.setZValue(1001)
        self.plot_widget.addItem(label)

        line_data = SlopeLineData(
            line_roi=line_roi, label=label, p1=(x1, y1), p2=(x2, y2)
        )

        line_roi.sigRegionChanged.connect(lambda: self._on_line_moved(line_data))
        line_roi.sigRemoveRequested.connect(lambda: self.remove_line(line_data))

        self._update_line_label(line_data)
        self.lines.append(line_data)
        self._notify_slopes_changed()

        return line_data


class SlopeLinesPanel(QtWidgets.QWidget):
    """
    Panel widget for controlling slope lines and displaying results.
    """

    # Signal emitted when user wants to apply slope to virtual gates
    slope_to_vgates_requested = QtCore.pyqtSignal(float, str, str)

    # Value representation options
    VALUE_REPRESENTATIONS = [
        ("slope", "slope", lambda s: s),
        ("inverse", "1/slope", lambda s: 1 / s if abs(s) > 1e-9 else float("inf")),
        ("negative", "-slope", lambda s: -s),
        (
            "neg_inverse",
            "-1/slope",
            lambda s: -1 / s if abs(s) > 1e-9 else float("-inf"),
        ),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.managers: List[SlopeLinesManager] = []
        self._raw_slopes: List[tuple] = []  # Store (label, raw_slope) pairs
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Enable/disable checkbox
        self.enable_checkbox = QtWidgets.QCheckBox("Enable slope lines")
        self.enable_checkbox.stateChanged.connect(self._on_enable_changed)
        layout.addWidget(self.enable_checkbox)

        # Value representation dropdown
        repr_layout = QtWidgets.QHBoxLayout()
        repr_layout.addWidget(QtWidgets.QLabel("Display:"))
        self.repr_selector = QtWidgets.QComboBox()
        for key, display_name, _ in self.VALUE_REPRESENTATIONS:
            self.repr_selector.addItem(display_name, key)
        self.repr_selector.currentIndexChanged.connect(self._on_repr_changed)
        repr_layout.addWidget(self.repr_selector)
        layout.addLayout(repr_layout)

        # Slopes display
        self.slopes_label = QtWidgets.QLabel("Slopes:")
        layout.addWidget(self.slopes_label)

        self.slopes_text = QtWidgets.QTextEdit()
        self.slopes_text.setReadOnly(True)
        self.slopes_text.setMaximumHeight(80)
        self.slopes_text.setPlaceholderText(
            "Draw lines on 2D plot to measure slopes.\nClick to start, click again to finish."
        )
        layout.addWidget(self.slopes_text)

        # Clear button
        self.clear_btn = QtWidgets.QPushButton("Clear All")
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        layout.addWidget(self.clear_btn)

        # Virtual gate application section
        vgate_group = QtWidgets.QGroupBox("Apply to Virtual Gates")
        vgate_layout = QtWidgets.QFormLayout(vgate_group)

        self.slope_selector = QtWidgets.QComboBox()
        self.slope_selector.setPlaceholderText("Select slope line")
        vgate_layout.addRow("Line:", self.slope_selector)

        self.apply_vgate_btn = QtWidgets.QPushButton("Apply to VGate Matrix")
        self.apply_vgate_btn.setToolTip(
            "Apply selected slope to virtual gate matrix window"
        )
        self.apply_vgate_btn.clicked.connect(self._on_apply_vgate_clicked)
        vgate_layout.addRow(self.apply_vgate_btn)

        # Status message label (replaces popup dialog)
        self.vgate_status_label = QtWidgets.QLabel("")
        self.vgate_status_label.setWordWrap(True)
        self.vgate_status_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        vgate_layout.addRow(self.vgate_status_label)

        layout.addWidget(vgate_group)

        # Stretch at bottom
        layout.addStretch()

    def register_manager(self, manager: SlopeLinesManager):
        """Register a slope lines manager to control."""
        self.managers.append(manager)
        manager.on_slope_changed = self._on_slopes_changed

    def unregister_manager(self, manager: SlopeLinesManager):
        """Unregister a slope lines manager."""
        if manager in self.managers:
            self.managers.remove(manager)
            manager.on_slope_changed = None

    def _on_enable_changed(self, state):
        """Handle enable checkbox state change."""
        enabled = state == QtCore.Qt.Checked
        for manager in self.managers:
            manager.enabled = enabled

    def _on_repr_changed(self, index: int):
        """Handle value representation change."""
        self._update_slopes_display()

    def _get_transform_func(self):
        """Get the current value transformation function."""
        key = self.repr_selector.currentData()
        for k, _, func in self.VALUE_REPRESENTATIONS:
            if k == key:
                return func
        return lambda s: s  # Default: identity

    def _format_value(self, raw_slope: float) -> str:
        """Format a slope value using current representation."""
        if abs(raw_slope) == float("inf"):
            return "∞"
        try:
            transformed = self._get_transform_func()(raw_slope)
            if abs(transformed) == float("inf"):
                return "∞"
            return f"{transformed:.4f}"
        except (ZeroDivisionError, ValueError):
            return "∞"

    def _on_slopes_changed(self, slopes: List[float]):
        """Handle slopes changed in any manager."""
        # Collect all raw slopes from all managers
        self._raw_slopes = []
        for manager in self.managers:
            for i, line in enumerate(manager.lines):
                label = f"Plot {self.managers.index(manager) + 1}, Line {i + 1}"
                self._raw_slopes.append((label, line.slope))

        self._update_slopes_display()

    def _update_slopes_display(self):
        """Update the slopes display with current representation."""
        # Update display
        if self._raw_slopes:
            text_lines = []
            for label, raw_slope in self._raw_slopes:
                value_str = self._format_value(raw_slope)
                text_lines.append(f"{label}: {value_str}")
            self.slopes_text.setText("\n".join(text_lines))
        else:
            self.slopes_text.clear()

        # Update selector (always show raw slope in selector for applying to VGM)
        self.slope_selector.clear()
        for label, raw_slope in self._raw_slopes:
            value_str = self._format_value(raw_slope)
            # Store raw slope as data, but display transformed value
            self.slope_selector.addItem(f"{label}: {value_str}", raw_slope)

    def _on_clear_clicked(self):
        """Clear all slope lines."""
        for manager in self.managers:
            manager.clear_all_lines()
        self.vgate_status_label.setText("")

    def _on_apply_vgate_clicked(self):
        """Apply selected slope to virtual gates."""
        idx = self.slope_selector.currentIndex()
        if idx < 0:
            self.vgate_status_label.setText(
                "<span style='color: orange;'>Select a slope line first.</span>"
            )
            return

        raw_slope = self.slope_selector.currentData()
        if raw_slope is None or abs(raw_slope) == float("inf"):
            self.vgate_status_label.setText(
                "<span style='color: red;'>Cannot apply infinite slope to virtual gates.</span>"
            )
            return

        # Get the transformed slope value based on current representation
        try:
            slope = self._get_transform_func()(raw_slope)
            if abs(slope) == float("inf"):
                self.vgate_status_label.setText(
                    "<span style='color: red;'>Cannot apply infinite value to virtual gates.</span>"
                )
                return
        except (ZeroDivisionError, ValueError):
            self.vgate_status_label.setText(
                "<span style='color: red;'>Cannot compute value for this slope.</span>"
            )
            return

        # Check if slope magnitude is valid for virtual gate matrix
        # Off-diagonal elements should be <= 1 (diagonal is always 1)
        if abs(slope) > 1.0:
            self.vgate_status_label.setText(
                "<span style='color: red;'>Value |{:.4f}| > 1. Off-diagonal elements must be ≤ 1. "
                "Try using 1/slope representation.</span>".format(slope)
            )
            return

        # Find the corresponding manager and line
        for manager in self.managers:
            if manager.lines:
                # Emit signal with slope and gate names
                self.slope_to_vgates_requested.emit(
                    slope, manager.x_label, manager.y_label
                )
                break

    def set_vgate_status(self, message: str, success: bool = True):
        """Set the status message for virtual gate application."""
        color = "green" if success else "orange"
        self.vgate_status_label.setText(
            f"<span style='color: {color};'>{message}</span>"
        )
