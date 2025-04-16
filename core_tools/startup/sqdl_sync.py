from core_tools.startup.config import get_configuration
from core_tools.startup.db_connection import connect_local_db
from core_tools.startup.sample_info import set_sample_info
from core_tools.startup.app_wrapper import run_app
from core_tools.data.sqdl.sqdl_sync import SQDLSync


def sync_init():
    set_sample_info('Any', 'Any', 'Any')
    connect_local_db()


def sync_main():
    config = get_configuration()
    writer = SQDLSync(config)
    writer.run()


if __name__ == '__main__':
    run_app('sqdl_sync', sync_init, sync_main)
