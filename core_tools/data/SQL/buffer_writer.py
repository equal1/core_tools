import numpy as np


class buffer_reference:
    def __init__(self, data):
        self.buffer = data
        self.buffer_lambda = buffer_reference.__empty_lambda

    @property
    def data(self):
        return self.buffer_lambda(self.buffer)

    @staticmethod
    def __empty_lambda(data):
        return data

    @staticmethod
    def averaging_lambda(dim):
        def avg_lambda(data):
            return np.average(data, axis=dim)
        return avg_lambda

    @staticmethod
    def slice_lambda(args):
        def slice_lambda(data):
            return data[tuple(args)]
        return slice_lambda

    @staticmethod
    def reshaper(shape):
        def reshape(data):
            return data.reshape(shape)
        return reshape


class buffer_writer(buffer_reference):
    def __init__(self, db_mgr, input_buffer):
        self.db_mgr = db_mgr
        self.buffer = input_buffer.ravel()
        self.buffer_lambda = buffer_reference.reshaper(input_buffer.shape)

        conn = db_mgr.connection
        lobject = conn.lobject(0, 'w')
        self.oid = lobject.oid
        lobject.close()
        self.cursor = 0
        self.cursor_db = 0

    def write(self, data):
        '''
        write n points to the buffer (no upload yet)

        Args:
            data (np.ndarray, ndim=1, dtype=double) : data to write
        '''
        self.buffer[self.cursor:self.cursor+data.size] = data
        self.cursor += data.size

    def sync(self):
        if self.cursor > self.cursor_db:
            conn = self.db_mgr.connection
            lobject = conn.lobject(self.oid, 'w')
            lobject.seek(self.cursor_db*8)
            lobject.write((self.buffer[self.cursor_db:self.cursor]).tobytes())
            lobject.close()
            self.cursor_db += self.cursor - self.cursor_db

    def close(self):
        pass


class buffer_reader(buffer_reference):
    def __init__(self, db_mgr, oid, shape, remote: bool = False):
        """Read data stream from database (large object).
        Args:
            remote: if True explictly use remote connection.
        """
        self.db_mgr = db_mgr
        self.buffer = np.full(shape, np.nan).ravel()
        self.buffer_lambda = buffer_reference.reshaper(shape)
        self.oid = oid
        self.remote = remote
        self.cursor = 0
        self.sync()

    def sync(self):
        '''
        update the buffer (for datasets that are still being written)
        '''
        conn = self.db_mgr.connection if not self.remote else self.db_mgr.remote_connection
        lobject = conn.lobject(self.oid, 'rb')
        lobject.seek(self.cursor*8)
        binary_data = lobject.read()
        data = np.frombuffer(binary_data)
        lobject.close()

        self.buffer[self.cursor:self.cursor+data.size] = data
        self.cursor = self.cursor+data.size

    def close(self):
        pass
