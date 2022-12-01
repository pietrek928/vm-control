from asyncio import create_task, set_event_loop, AbstractEventLoop, run_coroutine_threadsafe
from functools import partial
from inspect import isasyncgen
from time import perf_counter
from traceback import print_exception
from typing import Optional

from async_ import make_thread_loop
from gui import Gtk, gtk_func


class Task:
    def __init__(self, descr, progress=False):
        self.descr = descr
        self.task = None
        self.has_progress = progress
        self.progress_bar: Optional[Gtk.ProgressBar] = None
        self.msg_label: Optional[Gtk.Label] = None
        self.start_t = perf_counter()
        self.on_cancel = None

    def close_clicked(self, button: Gtk.Button):
        self.cancel()

    def render(self):
        grid = Gtk.Grid()
        grid.attach(Gtk.Label(self.descr), 0, 0, 5, 1)

        if self.has_progress:
            self.progress_bar = Gtk.ProgressBar()
            grid.attach(self.progress_bar, 0, 1, 4, 1)

        close = Gtk.Button(stock=Gtk.STOCK_CLOSE)
        close.connect('clicked', self.close_clicked)
        grid.attach(close, 4, 1, 1, 1)

        self.msg_label = Gtk.Label('')
        grid.attach(self.msg_label, 0, 2, 5, 1)

        return grid

    async def _wrap_task(self, coro):
        await coro
        self.cancel()

    def set_task(self, coro):
        self.task = create_task(self._wrap_task(coro))

    @gtk_func
    def set_progress(self, progress: float):
        if self.progress_bar is not None:
            self.progress_bar.set_fraction(progress)

    @gtk_func
    def set_message(self, msg: str):
        # TODO: history / log ?
        if self.msg_label is not None:
            self.msg_label.set_label(msg)

    @gtk_func
    def cancel(self):
        if self.task is not None:
            self.task.cancel()
        self.progress_bar = None
        self.msg_label = None
        if self.on_cancel is not None:
            self.on_cancel()


class TaskManager:
    def __init__(self):
        self.tasks = []
        self.box: Optional['Gtk.Box'] = None

    def render(self):
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        return self.box

    @gtk_func
    def remove_task(self, task, task_box):
        self.box.remove(task_box)
        self.tasks.remove(task)

    @gtk_func
    def add_task(self, task: Task):
        self.tasks.append(task)
        if self.box is not None:
            task_box = task.render()
            self.box.add(task_box)
            task.on_cancel = partial(self.remove_task, task, task_box)
            task_box.show_all()


def _start_background_loop(loop: AbstractEventLoop) -> None:
    set_event_loop(loop)
    loop.run_forever()


global_task_manager = TaskManager()
global_task_manager_loop = make_thread_loop()


async def _wrap_async_task(coro, task: Task):
    try:
        if isasyncgen(coro):
            async for msg in coro:
                task.set_message(str(msg))
        else:
            await coro
    except Exception as e:
        print_exception(e)
        print('!!!!!!!!!!', str(e))
        task.set_message(str(e))


async def _run_task(coro, task: Task):
    task.set_task(_wrap_async_task(coro, task))
    global_task_manager.add_task(task)


def run_task(coro, task: Task):
    run_coroutine_threadsafe(
        _run_task(coro, task),
        global_task_manager_loop
    )
