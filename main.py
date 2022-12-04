# ssh_cfg = SSHConfig({
#     'host': '10.1.5.25',
#     # 'compression': False,
# })
# ssh_cfg = SSHConfig({
#     'host': 'elektroinf.eu',
#     'username': 'root',
#     # 'compression': False,
# })
import time
from asyncio import sleep

import env  # noqa
import gpu  # noqa
import vm  # noqa
from gui import Gtk, HierarchyView, gtk_func, global_gtk_loop, stop_gtk_loop
from loader import ObjectLoader
from task_manager import global_task_manager, run_task, Task

# css = b'''
# .error {
#     color: red;
# }
# '''
# css_provider = Gtk.CssProvider()
# css_provider.load_from_data(css)
# context = Gtk.StyleContext()
# screen = Gdk.Screen.get_default()
# context.add_provider_for_screen(
#     screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
# )
#
# win = Gtk.Window()
# win.connect("destroy", Gtk.main_quit)
# win.add(env_cfg.render())
#
# win.show_all()
# Gtk.main()

# print(ssh_cfg.serialize())
#
# session = SSHSession(ssh_cfg)
# stdin, stdout, stderr = session.execute('echo aaaaaaaa $HOME $oo', envs=(
#     ('oo', '!!!!!!!!!!'),
# ))
# print(stdout.read())
# # tree = etree.parse(stdout)
# # print(tree.getroot())
# session.disconnect()

loader = ObjectLoader()

# host = SSHHost('test/host', loader, {
#     'host': '10.1.7.22',
#     'user': 'pietrek',
# })
# loader._loaded['test/host'] = host
# env = Env('test/host/env', loader, {
#     'dir': '.test-env',
#     'key': 'nv34yih4t34h'
# })
# loader._loaded['test/host/env'] = env
# test_vm = vm.QemuVM('test/host/env/vm', loader, {
#     'name': 'elo',
#     'drives': 'test_drive',
# })
# loader._loaded['test/host/env/vm'] = test_vm
# test_gpus = gpu.GPUS('test/host/gpus', loader, {})
# loader._loaded['test/host/gpus'] = test_gpus


#
# win = Gtk.Window()
# win.connect("destroy", Gtk.main_quit)
# win.add(host.render())
# win.show_all()
#
# win = Gtk.Window()
# win.connect("destroy", Gtk.main_quit)
# win.add(env.render())
# win.show_all()


@gtk_func
def create_windows():
    win = Gtk.Window()
    win.set_title('Task manager')
    win.add(global_task_manager.render())
    win.show_all()

    win = Gtk.Window()
    win.connect("destroy", stop_gtk_loop)
    win.add(HierarchyView(loader).render())
    win.show_all()


async def monitor(task: Task):
    a = 1
    while True:
        await sleep(1.)
        a += 1
        if a >= 100:
            a = 0
        task.set_progress(a / 100.)
        yield a


async def test():
    host = loader.load('', '/test/host')
    gpus = loader.load('', '/test/host/gpus')
    await gpus.detect_gpus()


task = Task('test1', progress=Task)
run_task(monitor(task), task)
run_task(test(), Task('test2'))

create_windows()

while global_gtk_loop.is_running():
    time.sleep(.1)

loader.save_all()

# print(
#     host.run_command('echo aaaaaaaaaaaaaaa')
# )
# print(host.run_command('trap "echo aaaaaaaaaaa" EXIT ; echo yoooooooo ; exit 1'))
