from asyncio import set_event_loop, AbstractEventLoop, new_event_loop, gather, all_tasks
from threading import Thread


def _start_background_loop(loop: AbstractEventLoop, coro) -> None:
    set_event_loop(loop)
    if coro is None:
        loop.run_forever()
    else:
        loop.run_until_complete(coro)
    pending = all_tasks(loop)
    loop.run_until_complete(gather(*pending))


def make_thread_loop(coro=None) -> AbstractEventLoop:
    loop = new_event_loop()
    thread = Thread(
        target=_start_background_loop, args=(loop, coro), daemon=True
    )
    thread.start()
    return loop
