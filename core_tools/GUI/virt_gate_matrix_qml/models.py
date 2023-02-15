from PyQt5 import QtCore
from dataclasses import dataclass

import numpy as np
import os
import logging

logger = logging.getLogger(__name__)

os.environ['QT_QUICK_CONTROLS_STYLE'] = 'Material'

@dataclass
class var_raw:
    name : str
    value : float
    step : int


class attenuation_model(QtCore.QAbstractListModel):
    Name  = QtCore.Qt.UserRole + 1
    Ratio = QtCore.Qt.UserRole + 2
    DB = QtCore.Qt.UserRole + 3

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self._data = data

    def rowCount(self, parent=None):
        return len(self._data)

    def data(self, QModelIndex, role):
        row = QModelIndex.row()
        if role == self.Name:
            return list(self._data.keys())[row]
        if role == self.Ratio:
            return "{}".format(round((list(self._data.values())[row]),3))
        if role == self.DB:
            return "{}".format(round(20*np.log10(list(self._data.values())[row]),1))

    def roleNames(self):
        return {
            QtCore.Qt.UserRole + 1: b'name',
            QtCore.Qt.UserRole + 2: b'ratio',
            QtCore.Qt.UserRole + 3: b'db',
        }

    # def reset_data(self, new_data):
    #     self.beginResetModel()
    #     self._data = new_data
    #     self.endResetModel()

    # def update_all_data(self):
    #     self.dataChanged.emit(self.index(0), self.index(self.rowCount()), self.roleNames())

    # def update_data(self, name, value, force=False):
    #     try:
    #         if float(value) == self._data[name].value and force==False:
    #             return
    #         print('updating {} to {}'.format(name, float(value)))
    #         self._data[name].value = float(value)
    #         idx = list(self._data.keys()).index(name)
    #         idx_qt = self.index(idx)
    #         self.dataChanged.emit(idx_qt, idx_qt, self.roleNames())
    #     except ValueError:
    #         print('Error {} could not be converted into a number.'.format(str(value)))

    # def __getitem__(self, item):
    #     idx = list(self._data.keys()).index(item)
    #     return list(self._data.values())[idx]

    @QtCore.pyqtSlot('int','QString', result=str)
    def process_attenuation_update_nrml(self, name, number):
        number = float(number)
        if number >= 1:
            self.set_ratio(name, 1.0)
            return '1.000'
        elif number <= 0.001 :
            self.set_ratio(name, 0.001)
            return '0.001'
        else:
            self.set_ratio(name, number)
            return f'{number:.3f}'

    @QtCore.pyqtSlot('int','QString', result=str)
    def process_attenuation_update_db(self, name, number):
        number = float(number)
        if number >= 0:
            self.set_ratio(name, 10**(0/20))
            return '0.0'
        elif number <= -60 :
            self.set_ratio(name, 10**(-60/20))
            return '-60.0'
        else:
            self.set_ratio(name, 10**(number/20))
            return f'{number:.1f}'

    def set_ratio(self, idx, value):
        try:
            self._data[idx] = value
        except Exception as e:
            print('Error occured during setting of variable for AWG to dac ratio')
            print(e)

class table_header_model(QtCore.QAbstractListModel):
    HeaderName = QtCore.Qt.UserRole + 1
    def __init__(self, names, parent=None):
        super().__init__(parent)
        self.names = names

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self.names)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if role == table_header_model.HeaderName:
            return self.names[index.row()]

    def roleNames(self):
        return {table_header_model.HeaderName : b'HeaderName'}

class vg_matrix_model(QtCore.QAbstractTableModel):
    vg_matrix_data = QtCore.Qt.UserRole + 1

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.__data = data
        self._data = self.__data
        self._v2r = False

        self._manipulate_callback = None

    def set_virtual_2_real(self, v2r):
        self._v2r = v2r

    def data(self, index, role):
        if role == vg_matrix_model.vg_matrix_data:
            val = self._data.get_element(index.row(), index.column(), v2r=self._v2r)
            rval = round(val, 3)
            if rval == 1:
                return '1'
            if rval == 0:
                return '0'

            return f'{val:.3f}'

    def setData(self, index, value, role):
        if role == QtCore.Qt.EditRole:
            idx0 = QtCore.QModelIndex()
            idx0.child(0,0)
            idx1  = QtCore.QModelIndex()
            idx1.child(0, 0)
            self.dataChanged.emit(idx0, idx1, [QtCore.Qt.EditRole])
            self.beginResetModel()
            self.endResetModel()

            return True

    @QtCore.pyqtSlot('int','int', 'QString')
    def update_vg_matrix(self, row, coll, value):
        value = float(value)
        self._data.set_element(row, coll, value, v2r=self._v2r)

    @QtCore.pyqtSlot('int')
    def normalize_matrix(self, normal):
        self._data = self.__data

        try:
            if normal:
                self._data.normalize()
            else:
                self._data.reverse_normalize()
            self.setData(None, 0, QtCore.Qt.EditRole)
        except:
            logger.error('normalize', exc_info=True)

    @QtCore.pyqtSlot('int')
    def invert_matrix(self, invert):
        self._data = self.__data

        try:
            self.set_virtual_2_real(invert)
            self.setData(None, 0, QtCore.Qt.EditRole)

            if self._manipulate_callback is not None:
                self._manipulate_callback()
        except:
            logger.error('invert', exc_info=True)

    def rowCount(self, index):
        return len(self._data.matrix)

    def columnCount(self, index):
        return len(self._data.matrix[0])

    def roleNames(self):
        return {vg_matrix_model.vg_matrix_data : b'vg_matrix_data'}