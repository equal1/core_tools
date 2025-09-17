from functools import cache
import core_tools.GUI.resources as resources
import os
import pathlib

from PyQt5 import QtGui, QtCore


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
    icon_unchecked_uri = pathlib.Path(os.path.join(icon_path, icon_unchecked)).as_uri()
    icon_checked_uri = pathlib.Path(os.path.join(icon_path, icon_checked)).as_uri()
    style_sheet = f"""
    QCheckBox::indicator {{
        width: {size}px;
        height: {size}px;
    }}
    QCheckBox::indicator:unchecked {{
        image: url("{icon_unchecked_uri[8:]}");
    }}
    QCheckBox::indicator:checked {{
        image: url("{icon_checked_uri[8:]}");
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
