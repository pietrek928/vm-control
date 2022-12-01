from asyncio import sleep
from functools import partial, wraps
from typing import TYPE_CHECKING, Optional, TypeVar

import gi

from async_ import make_thread_loop

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GObject  # noqa

if TYPE_CHECKING:
    from env import Env
    from host import SSHHost
    from loader import ObjectLoader

T = TypeVar('T')

gtk_run_loop = True


async def gtk_main_thread():
    while gtk_run_loop:
        while Gtk.events_pending():
            # if Gtk.main_iteration():
            #     print('exiting')
            #     return
            Gtk.main_iteration()
            await sleep(0.)
        await sleep(.01)


def stop_gtk_loop(obj):
    global gtk_run_loop
    gtk_run_loop = False


global_gtk_loop = make_thread_loop(gtk_main_thread())


def gtk_func(f):
    @wraps(f)
    def wrapped(*a, f=f, **k):
        global_gtk_loop.call_soon_threadsafe(partial(f, *a, **k))

    return wrapped


def decode_data(data: bytes):
    try:
        return data.decode('utf-8')
    except Exception:
        return str(data)


class Field:
    def __init__(self, default=None):
        self.default = default

    def serialize(self, v):
        return v

    def deserialize(self, v):
        return v

    def parse_input(self, v):
        return v

    def set_value(self, o, v):
        # MUST validate change !!!!!!!!!!!!
        pass

    def render(self):
        raise NotImplementedError(f'Render unimplemented for {self.__class__.__name__}')

    def add_set_cbk(self, o, set_cbk):
        pass

    def disable(self, o):
        pass

    def enable(self, o):
        pass


def gtk_entry_changed_cbk(set_cbk, entry):
    set_cbk(entry.get_text())


class BaseTextField(Field):
    def set_value(self, o, v):
        v = str(v)
        if v != v.strip():
            raise ValueError('white chars at the end or beginning')
        o.set_text(v)

    def render(self):
        return Gtk.Entry()

    def add_set_cbk(self, o, set_cbk):
        o.connect('changed', partial(gtk_entry_changed_cbk, set_cbk))

    def disable(self, o):
        o.set_sensitive(False)

    def enable(self, o):
        o.set_sensitive(True)


class StrField(BaseTextField):
    pass


class PassField(BaseTextField):
    def render(self):
        o = super().render()
        o.set_visibility(False)
        return o


class IntField(BaseTextField):
    def deserialize(self, v):
        return int(v)

    def parse_input(self, v):
        return int(v or 0)


class FloatField(BaseTextField):
    def deserialize(self, v):
        return float(v)

    def parse_input(self, v):
        return float(v or 0)


class EnField(BaseTextField):
    TRUE_VALUES = ('enabled', 'en', 'on', '1', 'true', 'ok')
    FALSE_VALUES = ('disabled', 'off', '0', 'false', 'no')

    def set_value(self, o, v):
        super().set_value(o, self.TRUE_VALUES[0] if v else self.FALSE_VALUES[0])

    def deserialize(self, v):
        if isinstance(v, bool):
            return v
        else:
            return self.parse_input(v)

    def parse_input(self, v):
        v_orig = v
        v = str(v).strip().lower()
        if v in self.TRUE_VALUES:
            return True
        elif v in self.FALSE_VALUES:
            return False
        else:
            raise ValueError(f'Count not convert `{v_orig}` to boolean')


def gtk_combo_changed_cbk(set_cbk, combo):
    tree_iter = combo.get_active_iter()
    if tree_iter is not None:
        model = combo.get_model()
        v = model[tree_iter][0]
        set_cbk(v)
    else:
        set_cbk(None)


class SelectField(Field):
    def __init__(self, *a, values=(), default=None, **k):
        if default is None:
            default = values[0]
        super().__init__(*a, default=default, **k)
        self._values = values

    def render(self):
        store = Gtk.ListStore(str)
        for v in self._values:
            store.append([v])

        combo = Gtk.ComboBox.new_with_model(store)
        cell = Gtk.CellRendererText()
        combo.pack_start(cell, True)
        combo.add_attribute(cell, "text", 0)
        return combo

    def add_set_cbk(self, o, set_cbk):
        o.connect('changed', partial(gtk_combo_changed_cbk, set_cbk))

    def disable(self, o):
        o.set_sensitive(False)

    def enable(self, o):
        o.set_sensitive(True)


class ObjectPickerField(Field):
    pass


def disconnect_signal(obj, signal_name):
    signal_id, detail = GObject.signal_parse_name(signal_name, obj, True)
    signal_id = GObject.signal_handler_find(obj, GObject.SignalMatchType.ID, signal_id, detail, None, None, None)
    if signal_id:
        GObject.signal_handler_disconnect(obj, signal_id)


def render_error_tooltip(msg, widget, x, y, keyboard_mode, tooltip):
    err_label = Gtk.Label(str(msg))
    err_label.get_style_context().add_class("error")
    tooltip.set_custom(err_label)
    return True


def add_error_tooltip(w, msg):
    disconnect_signal(w, 'query-tooltip')
    w.connect('query-tooltip', partial(render_error_tooltip, msg))
    w.set_property('has-tooltip', True)


def remove_error_tooltip(w):
    w.set_property('has-tooltip', False)
    disconnect_signal(w, 'query-tooltip')


class StateChange:
    def __init__(self, state_from, state_to):
        self.state_from = state_from
        self.state_to = state_to
        self.func = None

    def __call__(self, func):
        self.func = func
        return self


def _button_callback(self, state_to, descr, button):
    from task_manager import run_task, Task
    run_task(self.withstate(state_to), Task(descr))


class ConfigObject:
    def __init__(self, current_path: str, loader: 'ObjectLoader', data):
        super().__init__()
        self._current_path = current_path
        self._loader: 'ObjectLoader' = loader
        self._state = 'loaded'
        self.load_serialized(data)

    @classmethod
    def find_class_mapping(cls):
        mapping = {}
        to_visit = set(cls.__subclasses__())
        while to_visit:
            subcls = to_visit.pop()
            subcls_name = subcls.__name__
            if subcls.__name__ not in mapping:
                mapping[subcls_name] = subcls
                to_visit.update(subcls.__subclasses__())
        return mapping

    def load_serialized(self, data):
        cls = type(self)
        for k in vars(cls).keys():
            field_descr = getattr(cls, k, None)
            if isinstance(field_descr, Field):
                v = data.get(k)
                if v is not None:
                    try:
                        self.__dict__[k] = field_descr.deserialize(v)
                    except ValueError:
                        # TODO: handle parse error
                        pass
                else:
                    v = field_descr.default
                    if v is None:
                        raise ValueError(f'No default value for {k} in {cls.__name__}')
                    self.__dict__[k] = v

    def serialize(self):
        cls = type(self)
        data = dict(
            class_name=cls.__name__
        )
        for k, v in self.__dict__.items():
            field_descr = getattr(cls, k, None)
            if isinstance(field_descr, Field):
                data[k] = field_descr.serialize(v)
        return data

    def o(self, path):
        return self._loader.load(self._current_path, path)

    def set_value(self, name: str, field_descr: Field, field_in, v):
        try:
            v = field_descr.parse_input(v)
            self.__dict__[name] = v
            field_descr.set_value(field_in, v)
            field_in.get_style_context().remove_class("error")
            # field_in.set_property('has-tooltip', False)
            remove_error_tooltip(field_in)
        except ValueError as e:
            field_in.get_style_context().add_class("error")
            add_error_tooltip(field_in, e)
            # field_in.set_tooltip_text(str(e))

    def render(self):
        cls = type(self)
        grid = Gtk.Grid()
        grid.attach(Gtk.Label(''), 0, 0, 2, 1)
        n = 1

        for name, field_descr in vars(cls).items():
            if isinstance(field_descr, Field):
                descr_label = Gtk.Label(name)
                err_label = Gtk.Label('')
                err_label.get_style_context().add_class("error")
                field_in = field_descr.render()
                field_descr.add_set_cbk(
                    field_in, partial(self.set_value, name, field_descr, field_in)
                )
                v = self.__dict__.get(name)
                if v is not None:
                    field_descr.set_value(field_in, v)

                grid.attach(descr_label, 0, n, 1, 1)
                grid.attach(field_in, 1, n, 1, 1)
                n += 1

        # TODO: per state button ?
        for name, state_descr in vars(cls).items():
            if isinstance(state_descr, StateChange):
                button = Gtk.Button.new_with_label(label=name)
                button.connect(
                    "clicked", partial(
                        _button_callback, self, state_descr.state_to,
                        f'{self._current_path} -> {name}',
                    )
                )
                grid.attach(button, 0, n, 1, 1)
                n += 1

        return grid

    def get_special_path(self, special_name) -> Optional[str]:
        return None

    # TODO: analyze graph
    async def _go_to_state(self, f, t):
        if f == t:
            return

        print(f'{f} -> {t} ...')

        for prop in vars(type(self)).values():
            if isinstance(prop, StateChange) and prop.state_from == f and prop.state_to == t:
                await prop.func(self)
                return

        raise ValueError(f'Could not move state {f} -> {t}')

    async def withstate(self: T, state) -> T:  # TODO: use with scope ?
        await self._go_to_state(self._state, state)
        self._state = state
        return self

    async def get_host(self) -> 'SSHHost':
        return await self.o('$host').withstate('connected')

    async def get_env(self) -> 'Env':
        return await self.o('$env').withstate('unlocked')


class HierarchyView:
    def __init__(self, loader: 'ObjectLoader', base_path: str = '.'):
        self.loader = loader
        self.base_path = base_path

    def _append_empty(self, store: Gtk.TreeStore, iter):
        store.append(iter, ['.', None, None])

    def _open_path(self, path, store, tree_iter):
        for name, obj_path, obj in self.loader.load_dir(path):
            it = store.append(tree_iter, [name, obj_path, obj])
            if obj is None:
                self._append_empty(store, it)

    def treeview_expanded_cbk(self, tree_view: Gtk.TreeView, iter, path, store: Gtk.TreeStore):
        obj_path = tree_view.get_model().get_value(iter, 1)
        self._open_path(obj_path, store, iter)

    def treeview_collapsed_cbk(self, tree_view: Gtk.TreeView, iter, path, store: Gtk.TreeStore):
        while store.iter_has_child(iter):
            store.remove(store.iter_children(iter))
        self._append_empty(store, iter)

    def treeview_activated_cbk(self, tree_view: Gtk.TreeView, path, column, store: Gtk.TreeStore):
        obj = store[path][2]
        if obj is None:
            return

        obj_path = store[path][1]
        win = Gtk.Window(title=obj_path)
        # win.connect("destroy", Gtk.main_quit)
        win.add(obj.render())
        win.show_all()

    def render(self):
        store = Gtk.TreeStore(str, str, object)
        self._open_path('.', store, None)

        tv = Gtk.TreeView(store)
        render_text = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn('test')
        col.pack_start(render_text, True)
        col.add_attribute(render_text, "text", 0)
        tv.append_column(col)

        tv.connect('row-expanded', self.treeview_expanded_cbk, store)
        tv.connect('row-collapsed', self.treeview_collapsed_cbk, store)
        tv.connect('row-activated', self.treeview_activated_cbk, store)

        return tv
