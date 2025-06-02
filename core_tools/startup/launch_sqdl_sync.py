from core_tools.startup.app_launcher import launch_app

module_name = 'core_tools.startup.sqdl_sync'


def launch_sqdl_sync(kill=False, close_at_exit=False):
    launch_app('SQDL Sync', module_name,
               kill=kill, close_at_exit=close_at_exit)
