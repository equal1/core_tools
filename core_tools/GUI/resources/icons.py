import os
import pathlib
from functools import cache

from PyQt5 import QtCore, QtGui

import core_tools.GUI.resources as resources


def add_icon_to_button(button, icon_name):
    button.setIcon(get_icon(icon_name))
    button.setIconSize(QtCore.QSize(24, 24))


@cache
def get_icon(icon_name):
    icon_path = os.path.dirname(resources.__file__)
    return QtGui.QIcon(os.path.join(icon_path, icon_name))


@cache
def get_image(image_name, height=None):
    icon_path = os.path.dirname(resources.__file__)
    image = QtGui.QImage(os.path.join(icon_path, image_name))
    if height:
        image = image.scaledToHeight(height, mode=QtCore.Qt.SmoothTransformation)
    return image


def add_icons_to_checkbox(checkbox, icon_checked: str, icon_unchecked: str, size: int):
    icon_path = os.path.dirname(resources.__file__)

    def _icon_local_path(icon_name: str) -> str:
        return pathlib.Path(os.path.join(icon_path, icon_name)).as_posix()

    icon_unchecked_path = _icon_local_path(icon_unchecked)
    icon_checked_path = _icon_local_path(icon_checked)
    style_sheet = f"""
    QCheckBox::indicator {{
        width: {size}px;
        height: {size}px;
    }}
    QCheckBox::indicator:unchecked {{
        image: url("{icon_unchecked_path}");
    }}
    QCheckBox::indicator:checked {{
        image: url("{icon_checked_path}");
    }}
    """
    checkbox.setStyleSheet(style_sheet)


class Icons:
    @staticmethod
    def starred():
        return get_icon("Starred.png")

    @staticmethod
    def no_star():
        return get_icon("StarWhite.png")


class Images:
    @staticmethod
    def starred():
        return get_image("Starred.png", height=20)

    @staticmethod
    def no_star():
        return get_image("StarWhite.png", height=20)
