from dataclasses import dataclass, field
from typing import Any
import time

import threading
from queue import PriorityQueue


@dataclass(order=True)
class ExperimentJob:
    priority: float
    job: Any = field(compare=False)
    seq_nr: int = 0

    def __post_init__(self):
        # NOTE: use seq_nr to keep insertion order for jobs with equal priority
        self.seq_nr = ExperimentJob.seq_cntr
        ExperimentJob.seq_cntr += 1

    def kill(self):
        self.job.KILL = True

# NOTE: use seq_cntr to keep insertion order for jobs with equal priority
ExperimentJob.seq_cntr = 0


class queue_mgr():
    __instance = None
    __init = False

    def __new__(cls):
        if queue_mgr.__instance is None:
            queue_mgr.__instance = object.__new__(cls)
        return queue_mgr.__instance

    def __init__(self):
        if self.__init == False:
            print('Starting job queue_mgr')
            self.q = PriorityQueue()
            # Note: We have to use a dict, because the ExperimentJob only compares on priority
            self.job_refs = dict()

            def worker():
                while True:
                    n_jobs = self.q.qsize()
                    if n_jobs != 0:
                        job_object = self.q.get()
                        print(f'{n_jobs} items queued. Starting next job')
                        try:
                            if job_object.job.KILL != True:
                                job_object.job.run()
                        except Exception as e:
                            print(f'{type(e).__name__} {e} in job. Continuing with next job.')
                            print(e)
                        finally:
                            self.q.task_done()
                            try:
                                del self.job_refs[id(job_object)]
                            except: pass
                    else:
                        # 200ms sleep.
                        time.sleep(0.2)

            self.worker_thread = threading.Thread(target=worker, daemon=True).start()
            self.__init = True

    def put(self, job):
        '''
        put a job into the measurement queue

        Args:
            job (ExperimentJob) : job object
        '''
        self.q.put(job)
        self.job_refs[id(job)] = job

    def kill(self, job):
        '''
        kill a certain job that has been submitted to the queue

        Args:
            job (ExperimentJob) : job object
        '''
        job.KILL = True

    def killall(self):
        '''
        kill all the jobs
        '''
        job_refs = self.job_refs.copy()
        for job in job_refs.values():
            job.kill()

        self.job_refs = dict()
        print(f'Killed {len(job_refs)} jobs')

    def join(self):
        self.q.join()

    @property
    def n_jobs(self):
        return self.q.qsize()


#%%
if __name__ == '__main__':
    from core_tools.sweeps.sweeps import do1D, do2D
    import os
    import qcodes as qc
    from qcodes.dataset.sqlite.database import initialise_or_create_database_at
    from qcodes.dataset.experiment_container import load_or_create_experiment
    from qcodes.instrument.specialized_parameters import ElapsedTimeParameter

    # class MyCounter(qc.Parameter):
    #     def __init__(self, name):
    #         # only name is required
    #         super().__init__(name, label='Times this has been read',
    #                          docstring='counts how many times get has been called '
    #                                    'but can be reset to any integer >= 0 by set')
    #         self._count = 0

    #     # you must provide a get method, a set method, or both.
    #     def get_raw(self):
    #         self._count += 1
    #         return self._count

    #     def set_raw(self, val):
    #         self._count = val

    # tutorial_db_path = os.path.join(os.getcwd(), 'linking_datasets_tutorial.db')
    # initialise_or_create_database_at(tutorial_db_path)
    # load_or_create_experiment('tutorial', 'no sample')

    # my_param = MyCounter('test_instr')

    # x = qc.Parameter(name='x', label='Voltage_x', unit='V',
    #           set_cmd=None, get_cmd=None)
    # y = qc.Parameter(name='y', label='Voltage_y', unit='V',
    #           set_cmd=None, get_cmd=None)
    # timer = ElapsedTimeParameter('time')

    # scan1 = do2D(x, 0, 20, 20, 0.0, y, 0, 80, 30, 0.1, my_param)
    # scan2 = do2D(x, 0, 20, 20, 0.0, timer, 0, 80, 30, .1, my_param)
    # scan3 = do1D(x, 0, 100, 50, 0.1 , my_param, reset_param=True)

    # q = queue_mgr()
    # job1 = ExperimentJob(1, scan1)
    # job2 = ExperimentJob(1, scan2)
    # job3 = ExperimentJob(1, scan3)
    # q.put(job1)
    # q.put(job2)
    # q.put(job3)

    # q.killall()
    # scan1 = do2D(x, 0, 20, 20, 0.0, y, 0, 80, 30, 0.1, my_param)
    # scan2 = do2D(x, 0, 20, 20, 0.0, timer, 0, 80, 30, .1, my_param)
    # job1 = ExperimentJob(1, scan1)
    # job2 = ExperimentJob(1, scan2)
    # q.put(job1)
    # q.put(job2)