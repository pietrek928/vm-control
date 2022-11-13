import json
from collections import defaultdict
from os import makedirs, listdir
from os.path import isdir
from typing import Dict, Tuple, Iterable, DefaultDict, Set

from gui import ConfigObject


class ObjectLoader:
    def __init__(self, config_dir: str = '.'):
        self._loaded: Dict[str, ConfigObject] = {}
        self._needed_by: DefaultDict[str, Set[str]] = defaultdict(set)
        self._config_dir = config_dir

    def _simplify_path(self, components: Iterable[str]):
        parsed = []
        for c in components:
            c = c.strip()
            if c == '.':
                continue
            elif c == '..':
                parsed = parsed[:-1]
            else:
                parsed.append(c)
        return tuple(parsed)

    def _parse_path(self, path: str) -> Tuple[str, ...]:
        components = list(
            c.strip() for c in path.split('/')
        )
        if not components[0]:
            components[0] = '$root'
        return tuple(components)

    # TODO: detect dependency cycles
    def _resolve_path(
            self, current_path: Tuple[str, ...], path: Tuple[str, ...]
    ) -> Tuple[str, ...]:
        if path and path[0].startswith('$'):
            return self._simplify_path(
                self._find_special(current_path, path[0][1:]) + path[1:]
            )
        else:
            return self._simplify_path(current_path + path)

    def _find_special(
            self, path_components: Tuple[str, ...], special_name: str
    ):
        if special_name == 'root':  # TODO: register somewhere
            return ()

        for i in reversed(range(len(path_components))):
            components = path_components[:i + 1]
            path_name = '/'.join(components)
            if path_name in self._loaded:
                obj = self._loaded[path_name]
                resolved = obj.get_special_path(special_name)
                if resolved is not None:
                    return self._resolve_path(components, self._parse_path(resolved))

        raise ValueError(
            f'Cannot resolve `${special_name}` at `{"/".join(path_components)}`'
        )

    def _load_object(self, path):
        with open(f'{path}.json', 'r') as f:
            config_data = json.load(f)

        obj_class_name = config_data.pop('class_name')
        obj_cls = ConfigObject.find_class_mapping()[obj_class_name]
        return obj_cls(path, self, config_data)

    def load(self, current_path: str, path: str):
        resolved = self._resolve_path(
            self._parse_path(current_path), self._parse_path(path)
        )
        resolved_path = '/'.join(resolved)
        self._needed_by[resolved_path].add(current_path)
        if resolved_path in self._loaded:
            obj = self._loaded[resolved_path]
        else:
            obj = self._load_object(resolved_path)
            self._loaded[resolved_path] = obj

        return obj

    def load_dir(self, dir_path):
        for fname in listdir(dir_path):
            path = f'{dir_path}/{fname}'
            if isdir(path):
                yield fname, path, None
            else:
                if fname.endswith('.json'):
                    yield fname[:-5], path[:-5], self.load('.', path[:-5])

    def save_all(self):
        for p, o in self._loaded.items():
            if '/' in p:
                makedirs(p.rsplit('/', 1)[0], exist_ok=True)
            with open(f'{p}.json', 'w') as f:
                json.dump(o.serialize(), f)

    def unload(self, current_path: str, path: str):
        resolved = self._resolve_path(
            self._parse_path(current_path), self._parse_path(path)
        )
        resolved_path = '/'.join(resolved)
        self._needed_by[resolved_path].remove(current_path)
        # TODO: garbage collect
