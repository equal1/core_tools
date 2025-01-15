from core_tools.data.SQL.SQL_connection_mgr import SQL_database_manager
from psycopg2.extras import RealDictCursor


class SqlConnection:

    def __init__(self, remote=False):
        self.remote = remote

    def execute_query(self, statement, vars=None, return_dict=False):
        try:
            connection = SQL_database_manager().conn_remote if self.remote else SQL_database_manager().conn_local
            if return_dict:
                cur = connection.cursor(cursor_factory=RealDictCursor)
            else:
                cur = connection.cursor()
            cur.execute(statement, vars=vars)
            res = cur.fetchall()
            cur.close()
            return res
        except Exception:
            connection.close()
            raise

    def execute_statement(self, statement, vars=None) -> int:
        try:
            connection = SQL_database_manager().conn_remote if self.remote else SQL_database_manager().conn_local
            cur = connection.cursor()
            cur.execute(statement, vars=vars)
            result = cur.rowcount
            cur.close()
            return result
        except Exception:
            connection.close()
            raise

    def insert_or_update(self, table_name, insert_only_values, update_values,
                         modify_count=False):
        insert_columns = list(insert_only_values.keys()) + list(update_values.keys())
        placeholders = ['%(' + column + ')s' for column in insert_columns]
        updates = [column + '=%(' + column + ')s' for column in insert_columns]
        vars = dict(insert_only_values)
        vars.update(update_values)
        if modify_count:
            updates.append(f'modify_count = {table_name}.modify_count + 1')
        statement = f'''
            INSERT INTO {table_name} ({', '.join(insert_columns)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT (uuid) DO UPDATE
            SET {', '.join(updates)}
            '''
        self.execute_statement(statement, vars)

    def commit(self):
        try:
            connection = SQL_database_manager().conn_remote if self.remote else SQL_database_manager().conn_local
            connection.commit()
        except Exception:
            connection.close()
            raise

    def abort(self):
        try:
            connection = SQL_database_manager().conn_remote if self.remote else SQL_database_manager().conn_local
            connection.rollback()
        except Exception:
            connection.close()
            raise

    def close(self):
        connection = SQL_database_manager().conn_remote if self.remote else SQL_database_manager().conn_local
        connection.close()
