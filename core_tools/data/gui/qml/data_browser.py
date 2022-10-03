from PyQt5 import QtCore, QtWidgets, QtQml
from core_tools.data.gui.qml.models import date_model, data_overview_model, combobox_model
from core_tools.data.gui.qml.GUI_controll import signale_handler, DataFilter
import os
import core_tools.data.gui.qml as qml_in

from core_tools.data.SQL.connect import SQL_conn_info_local, sample_info, set_up_local_storage

def coalesce(*args):
    for arg in args:
        if arg is not None:
            return arg
    return None


class data_browser():
    def __init__(self,
                 project=None, set_up=None, sample=None,
                 window_location=None, window_size=None):
        super().__init__()

        self.app = QtCore.QCoreApplication.instance()
        self.instance_ready = True
        if self.app is None:
            self.instance_ready = False
            self.app = QtWidgets.QApplication([])

        self.engine = QtQml.QQmlApplicationEngine()

        self.date_model = date_model([])
        self.data_overview_model = data_overview_model([])

        self.project_model = combobox_model()
        self.set_up_model = combobox_model()
        self.sample_model = combobox_model()

        self.data_filter = DataFilter(self.project_model, self.set_up_model, self.sample_model)
        self.data_filter.set_project(coalesce(project, sample_info.project))
        self.data_filter.set_set_up(coalesce(set_up, sample_info.set_up))
        self.data_filter.set_sample(coalesce(sample, sample_info.sample))

        self.signal_handler = signale_handler(self.data_filter,
                                              self.date_model, self.data_overview_model)

        self.engine.rootContext().setContextProperty("combobox_project_model", self.project_model)
        self.engine.rootContext().setContextProperty("combobox_set_up_model", self.set_up_model)
        self.engine.rootContext().setContextProperty("combobox_sample_model", self.sample_model)

        self.engine.rootContext().setContextProperty("date_list_model", self.date_model)
        self.engine.rootContext().setContextProperty("data_content_view_model", self.data_overview_model)

        self.engine.rootContext().setContextProperty("local_conn_status", True)
        self.engine.rootContext().setContextProperty("remote_conn_status", True)

        self.engine.rootContext().setContextProperty("signal_handler", self.signal_handler)

        # grab directory from the import!
        filename = os.path.join(qml_in.__file__[:-11], "data_browser.qml")
        self.engine.load(QtCore.QUrl.fromLocalFile(filename))
        self.win = self.engine.rootObjects()[0]
        self.signal_handler.init_gui_variables(self.win)
        if window_location is not None:
            self.win.setPosition(window_location[0], window_location[1])
        if window_size is not None:
            self.win.setWidth(window_size[0])
            self.win.setHeight(window_size[1])

        if self.instance_ready == False:
            self.app.exec_()


if __name__ == "__main__":
    from core_tools.data.SQL.connect import SQL_conn_info_local, set_up_remote_storage, sample_info, set_up_local_storage
    set_up_remote_storage('131.180.205.81', 5432, 'xld_measurement_pc', 'XLDspin001', 'spin_data', "6dot", "XLD", "6D3S - SQ20-20-5-18-4")
    # set_up_local_storage('stephan', 'magicc', 'test', 'Intel Project', 'F006', 'SQ38328342')
    # set_up_remote_storage('131.180.205.81', 5432, 'xld_measurement_pc', 'XLDspin001', 'spin_data', "6dot", "XLD", "6D3S - SQ20-20-5-18-4")
    # set_up_remote_storage('131.180.205.81', 5432, 'stephan_test', 'magicc', 'spin_data_test', 'Intel Project', 'F006', 'SQ38328342')

    g = data_browser()