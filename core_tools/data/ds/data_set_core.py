from datetime import datetime
import logging
import time

from core_tools.data.ds.data_set_DataMgr import m_param_organizer, dataset_data_description
from core_tools.data.SQL.SQL_dataset_creator import SQL_dataset_creator


logger = logging.getLogger(__name__)


class data_set:

    def __init__(self, ds_raw):
        self.id = None
        self.__data_set_raw = ds_raw
        self.__repr_attr_overview = []
        self.__init_properties(m_param_organizer(ds_raw.measurement_parameters_raw))
        self.last_commit = time.time()

    @property
    def completed(self):
        return self.__data_set_raw.completed

    @property
    def dbname(self):
        return self.__data_set_raw.dbname

    @property
    def table_name(self):
        return self.__data_set_raw.SQL_table_name

    @property
    def name(self):
        return self.__data_set_raw.exp_name

    @property
    def exp_id(self):
        return self.__data_set_raw.exp_id

    @property
    def exp_uuid(self):
        return self.__data_set_raw.exp_uuid

    @property
    def exp_name(self):
        return self.__data_set_raw.exp_name

    @property
    def project(self):
        return self.__data_set_raw.project

    @property
    def set_up(self):
        return self.__data_set_raw.set_up

    @property
    def scope(self):
        return self.__data_set_raw.scope

    @property
    def sample_name(self):
        return self.__data_set_raw.sample

    @property
    def metadata(self):
        return self.__data_set_raw.metadata

    @property
    def snapshot(self):
        return self.__data_set_raw.snapshot

    @property
    def keywords(self):
        return self.__data_set_raw.keywords

    @property
    def starred(self):
        return self.__data_set_raw.starred

    @property
    def run_timestamp(self):
        return datetime.fromtimestamp(self.__data_set_raw.UNIX_start_time)

    @property
    def run_timestamp_raw(self):
        return self.__data_set_raw.UNIX_start_time

    @property
    def completed_timestamp(self):
        return datetime.fromtimestamp(self.__data_set_raw.UNIX_stop_time)

    @property
    def completed_timestamp_raw(self):
        return self.__data_set_raw.UNIX_stop_time

    def __len__(self):
        return len(self.__repr_attr_overview)

    def __getitem__(self, i):
        if isinstance(i, str):
            return self(i)

        return self.__repr_attr_overview[i]

    def __init_properties(self, data_set_content):
        '''
        populates the dataset with the measured parameter in the raw dataset

        Args:
            data_set_content (m_param_organizer) : m_param_raw raw objects in their mamagement object
        '''
        m_ids = data_set_content.get_m_param_id()

        for i, m_id in enumerate(m_ids, 1):
            n_sets = len(data_set_content[m_id])
            repr_attr_overview = []
            for j in range(n_sets):
                ds_descript = dataset_data_description('', data_set_content.get(m_id,  j), data_set_content)

                name = 'm' + str(i) + "_" + str(j+1)
                setattr(self, name, ds_descript)

                if j == 0:
                    setattr(self, 'm' + str(i), ds_descript)

                if j == 0 and n_sets == 1:  # consistent printing
                    repr_attr_overview += [('m' + str(i), ds_descript)]
                    ds_descript.name = 'm' + str(i)
                else:
                    repr_attr_overview += [(name, ds_descript)]
                    ds_descript.name = name

            self.__repr_attr_overview += [repr_attr_overview]

    def __call__(self, label_variable):
        '''
        extract a meaurement by its label
        '''
        for minstr in self.__repr_attr_overview:
            for var_meas in minstr:
                if var_meas[1].label == label_variable or var_meas[1].name == label_variable:
                    return var_meas[1]

        raise ValueError(f'Unable to find \'{label_variable}\' in ds with id :{self.exp_id}')

    def add_result(self, input_data):
        '''
        Add results to the dataset

        Args:
            input_data (dict<int, list<np.ndarray>>):
                dict with as key the id of the measured parameter and the data that is measured.
        '''
        for m_param in self.__data_set_raw.measurement_parameters:
            if m_param.id_info in input_data.keys():
                m_param.write_data(input_data)

        self.__write_to_db()

    def skip_result(self, input_data):
        '''
        Adds NaN values to dataset for the size of the parameters.
        '''
        for m_param in self.__data_set_raw.measurement_parameters:
            if m_param.id_info in input_data.keys():
                m_param.skip_data(input_data)

    def mark_completed(self):
        '''
        mark dataset complete. Stop updating the database and allow garbage collector to release memory.
        '''
        try:
            self.__write_to_db(True)
        finally:
            self.__data_set_raw.completed = True
            SQL_ds_creator = SQL_dataset_creator()
            SQL_ds_creator.finish_measurement(self.__data_set_raw)

    def sync(self):
        '''
        Updates dataset in case only part of the points were downloaded.
        '''
        if not self.completed:
            SQL_ds_creator = SQL_dataset_creator()
            self.completed = SQL_ds_creator.is_completed(self.exp_uuid)
            self.__data_set_raw.sync_buffers()

    def __write_to_db(self, force: bool = False):
        '''
        update values every 200ms to the database.

        Args:
            force (bool) : enforce the update
        '''
        current_time = time.time()
        # increase flush interval for long measurements to reduce overhead
        run_duration = current_time - self.__data_set_raw.UNIX_start_time
        flush_interval = 0.25
        if run_duration > 10.0:
            flush_interval *= 2
        if run_duration > 30.0:
            flush_interval *= 2
        if current_time - self.last_commit > flush_interval or force:
            t_start = time.perf_counter()
            self.__data_set_raw.sync_buffers()
            SQL_ds_creator = SQL_dataset_creator()
            SQL_ds_creator.update_write_cursors(self.__data_set_raw)
            self.last_commit = time.time()
            duration = time.perf_counter() - t_start
            if duration > 0.1:
                logger.info(f"Write to db took {duration:.3f} s")

    def __repr__(self):
        output_print = f"DataSet :: {self.name}\n\nid = {self.exp_id}\nuuid = {self.exp_uuid}\n\n"
        output_print += "| idn             | label           | unit     | size                     |\n"
        output_print += "---------------------------------------------------------------------------\n"
        for i in self.__repr_attr_overview:
            for j in i:
                output_print += j[1].__repr__()
                output_print += "\n"

        output_print += f"set_up : {self.set_up}\n"
        output_print += f"project : {self.project}\n"
        output_print += f"sample_name : {self.sample_name}\n"
        return output_print

    def close(self):
        self.__data_set_raw.close()
