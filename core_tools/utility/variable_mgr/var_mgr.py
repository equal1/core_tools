from core_tools.data.SQL.connect import SQL_conn_info_local, SQL_conn_info_remote, sample_info
from core_tools.data.SQL.SQL_connection_mgr import SQL_database_manager


from core_tools.utility.variable_mgr.var_mgr_sql import var_sql_queries
from core_tools.utility.variable_mgr.qml.gui_controller import GUI_controller
import psycopg2

class variable_descriptor:
    def __init__(self, name, unit, category,step, value=0, skip_init=False):
        self.name = name
        self.unit = unit
        self.step = step
        self.category = category

        if skip_init == False:
            var_sql_queries.add_variable(variable_mgr().conn_local, name , unit, category, step, value)
    
    def __get__(self, obj, objtype=None):
        return obj.vars[self.name]

    def __set__(self, obj, value):
        all_vals, last_id = var_sql_queries.update_val(variable_mgr().conn_local, self.name, value)
        
        obj.update_GUI()
        obj.vars = dict(all_vals)

    @property
    def value(self):
        return self.__get__(variable_mgr())

    @value.setter
    def value(self, value):
        return self.__set__(variable_mgr(),value)

    def __repr__(self):
        return f'{self.__class__}: {self.name}: {self.value} [{self.unit}]'

    def __str__(self):
        return f'{self.name}: {self.value} [{self.unit}]'

class variable_mgr():
    __instance = None
    conn_local = None

    def __new__(cls):
        if variable_mgr.__instance is None:
            variable_mgr.__instance = object.__new__(cls)
        return variable_mgr.__instance

    def __init__(self):
        # fetch the connection from the database object, no need to connect multiple times.
        if self.conn_local is None:
            self.conn_local = SQL_database_manager().conn_local
            
            self.__GUI = None
            self.data = dict()
            self.vars = dict()
            self.__load_variables()
        elif self.conn_local.closed:
            self.conn_local = SQL_database_manager().conn_local

    def __repr__(self):
        c=self.__class__
        name = c.__module__ + '.' + c.__name__
        return f'<{name} at {id(self):x}>: {self.number_of_categories} categories, {self.number_of_variables} variables'

    @property
    def number_of_variables(self) -> int:
        return sum( len(item) for item in self.data.values() )

    @property
    def number_of_categories(self) -> int:
        return len(self.data)

    def __load_variables(self):
        var_sql_queries.init_table(self.conn_local)
        all_specs = var_sql_queries.get_all_specs(self.conn_local)
        for item in all_specs:
            self.add_variable(item['category'], item['name'], item['unit'], item['step'], skip_init=True)
        self.vars = var_sql_queries.get_all_values(self.conn_local)
        
    def show(self):
        self.__GUI = GUI_controller(self.data)
    
    def update_GUI(self):
        if self.__GUI is not None:
            self.__GUI.set_data()

    def update_column_name(self, old, new):
        var_sql_queries.change_column_name(self.conn_local, old, new)

    def add_variable(self, category, name ,unit, step, value=0, skip_init=False):
        if not hasattr(self, name):
            my_desc = variable_descriptor(name, unit, category,step, value, skip_init)
            if category not in self.data.keys():
                self.data[category] = dict()
            self.data[category][name] = my_desc
            setattr(self, name, my_desc)
            if skip_init == False:
                self.vars = var_sql_queries.get_all_values(self.conn_local)
                if self.__GUI is not None:
                    self.__GUI.set_data()
        else:
            print(f'trying to add variable {name} that is already there')

    def remove_variable(self, variable_name):
        obj = super().__getattribute__(variable_name)
        
        self.data[obj.category].pop(variable_name, None)
        if len(self.data[obj.category]) == 0:
            self.data.pop(obj.category, None)
        self.vars.pop(variable_name, None)

        var_sql_queries.remove_variable(self.conn_local, variable_name)
        super().__delattr__(variable_name)
        
        if self.__GUI is not None:
                    self.__GUI.set_data()

    def __getitem__(self, item):
        return getattr(self, item)
    
    def __getattribute__(self, name): #little hack to make make the descriptors work.
        attr = super().__getattribute__(name)
        if isinstance(attr, variable_descriptor):
            return attr.__get__(self, attr)
        return attr

    def __setattr__(self, name, value): #little hack to make make the descriptors work.
        try:
            attr = super().__getattribute__(name)
            return attr.__set__(self, value)
        except AttributeError:
            return super().__setattr__(name, value)

if __name__ == '__main__':
    from core_tools.data.SQL.connect import set_up_local_storage, set_up_remote_storage
    # set_up_local_storage('stephan', 'magicc', 'test', 'project', 'set_up', 'sample')
    set_up_local_storage("xld_user", "XLDspin001", "vandersypen_data", "6dot", "XLD", "6D3S - SQ20-20-5-18-4")

    t = variable_mgr()

    # print(t.SD1_P_on)
    # t.remove_variable("SD1_P_off")
    # t.remove_variable('SD1_P_off')
    # t.remove_variable('SD1_P_on_11')
    # t.remove_variable('SD1_P_on_10')
    # t.remove_variable('U1')
    # t.remove_variable('U2')
    # t.remove_variable('U3')
    # t.remove_variable('U4')
    # t.add_variable("SD voltages", "SD1_P_off", 'mV', 0.1)
    # t.add_variable("SD voltages", "SD1_P_on_11", 'mV', 0.1)
    # t.add_variable("SD voltages", "SD1_P_on_10", 'mV', 0.1)
    
    # t.add_variable("Dot properties", "U1", 'mV', 1)
    # t.add_variable("Dot properties", "U2", 'mV', 1)
    # t.add_variable("Dot properties", "U3", 'mV', 1)
    # t.add_variable("Dot properties", "U4", 'mV', 1)

    # t.show()

    # import time

    # time.sleep(2)
    # t.SD1_P_off = 5

    # time.sleep(2)
    # t.SD1_P_off = 2
