from core_tools.data.SQL.SQL_common_commands import execute_statement, execute_query
from core_tools.data.SQL.SQL_common_commands import select_elements_in_table, insert_row_in_table, update_table
from core_tools.data.SQL.connect import sample_info

import psycopg2
import json
import numpy as np


class virtual_gate_queries:
    @staticmethod
    def generate_table(conn):
        statement = "CREATE TABLE if not EXISTS {} (".format(virtual_gate_queries.table_name())
        statement += "name text NOT NULL UNIQUE,"
        statement += "real_gates bytea ,"
        statement += "virtual_gates bytea ,"
        statement += "vg_matrix bytea );"

        execute_statement(conn, statement)
        conn.commit()

    @staticmethod
    def get_virtual_gate_matrix(conn, name):
        res = select_elements_in_table(conn, virtual_gate_queries.table_name(
        ),  ('real_gates', 'virtual_gates', 'vg_matrix'), where=('name', name))

        if len(res) == 0:  # if empty
            return list(), list(), np.asarray([[],])

        return (
            json.loads(res[0]['real_gates'].tobytes()),
            json.loads(res[0]['virtual_gates'].tobytes()),
            np.asarray(json.loads(res[0]['vg_matrix'].tobytes())),
            )

    @staticmethod
    def set_virtual_gate_matrix(conn, name, real_gates, virtual_gates, vg_matrix):

        var_names = ('name', 'real_gates', 'virtual_gates', 'vg_matrix')

        var_values = (name, psycopg2.Binary('{}'.format(json.dumps(real_gates)).encode('ascii')),
                      psycopg2.Binary(json.dumps(virtual_gates).encode('ascii')),
                      psycopg2.Binary(json.dumps(vg_matrix.tolist()).encode('ascii')))

        if not virtual_gate_queries.check_var_in_table_exist(conn, name):
            insert_row_in_table(conn, virtual_gate_queries.table_name(), ('name',), (name,))
        update_table(conn, virtual_gate_queries.table_name(), var_names, var_values, condition=('name', name))

        conn.commit()

    @staticmethod
    def check_var_in_table_exist(conn, name):
        return_data = select_elements_in_table(
            conn, virtual_gate_queries.table_name(), ('name', ), where=('name', name), dict_cursor=False)

        if len(return_data) == 0 or return_data[0][0] is None:
            return False
        return True

    @staticmethod
    def delete_virtual_matrix(conn, name):
        table = virtual_gate_queries.table_name()
        execute_statement(
            conn,
            f"DELETE FROM {table} WHERE name=%s",
            placeholders=[name]
        )

    @staticmethod
    def check_table_exist(conn):
        return_data = execute_query(conn, "SELECT to_regclass('{}');".format(virtual_gate_queries.table_name()))

        if len(return_data) == 0 or return_data[0][0] is None:
            return False
        return True

    @staticmethod
    def table_name():
        sample, set_up, project = sample_info.sample, sample_info.set_up, sample_info.project
        return (set_up+project+sample+'_virtual_gates').replace(" ", "_").replace('-', '_')


class AWG_2_dac_ratio_queries:
    @staticmethod
    def generate_table(conn):
        statement = "CREATE TABLE if not EXISTS {} (".format(AWG_2_dac_ratio_queries.table_name())
        statement += "name text NOT NULL UNIQUE,"
        statement += "real_gates bytea ,"
        statement += "ratios bytea );"

        execute_statement(conn, statement)
        conn.commit()

    @staticmethod
    def get_AWG_2_dac_ratios(conn, name):
        res = select_elements_in_table(conn, AWG_2_dac_ratio_queries.table_name(),
                                       ('real_gates', 'ratios'), where=('name', name))

        gate_ratio_pairs = dict()

        if len(res) != 0:
            gates, ratios = json.loads(res[0]['real_gates'].tobytes()), json.loads(res[0]['ratios'].tobytes())
            for i in range(len(gates)):
                gate_ratio_pairs[gates[i]] = ratios[i]

        return gate_ratio_pairs

    @staticmethod
    def set_AWG_2_dac_ratios(conn, name, gate_ratio_pairs):
        gates = list(gate_ratio_pairs.keys())
        ratios = list(gate_ratio_pairs.values())

        var_names = ('name', 'real_gates', 'ratios')
        var_values = (name, psycopg2.Binary(json.dumps(gates).encode('ascii')),
                      psycopg2.Binary(json.dumps(list(ratios)).encode('ascii')))

        if not AWG_2_dac_ratio_queries.check_exist(conn, name):
            insert_row_in_table(conn, AWG_2_dac_ratio_queries.table_name(), ('name',), (name, ))
        update_table(conn, AWG_2_dac_ratio_queries.table_name(), var_names, var_values, condition=('name', name))

        conn.commit()

    @staticmethod
    def check_exist(conn, name):
        return_data = execute_query(conn, "SELECT name FROM {} WHERE name = '{}';".format(
            AWG_2_dac_ratio_queries.table_name(), name))

        if len(return_data) == 0 or return_data[0][0] is None:
            return False
        return True

    @staticmethod
    def table_name():
        sample, set_up, project = sample_info.sample, sample_info.set_up, sample_info.project
        return (set_up+project+sample+'_AWG_to_DAC_ratios').replace(" ", "_").replace('-', '_')
