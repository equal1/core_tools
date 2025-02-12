from core_tools.startup.db_connection import connect_local_db
from core_tools.startup.sample_info import set_sample_info
from core_tools.startup.app_wrapper import run_app
from core_tools.data.sqdl.sqdl_writer import SQDLWriter


def sync_init():
    # todo: validate if setting sample info is still required
    set_sample_info('Any', 'Any', 'Any')
    connect_local_db()
    print('Starting SQDL Sync')


def sync_main():
    writer = SQDLWriter()
    writer.run()


if __name__ == '__main__':
    run_app('sqdl_sync', sync_init, sync_main)
