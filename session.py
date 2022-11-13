from typing import Tuple


class CommandError(Exception):
    pass


class Session:
    def execute(
            self, cmd, timeout=None, envs: Tuple[Tuple[str, str], ...] = ()
    ):  # -> Tuple[ChannelStdinFile, ChannelFile, ChannelStderrFile]:
        raise NotImplementedError('Execute not implemented')

    def disconnect(self):
        raise NotImplementedError('Disconnect not implemented')


class SessionProcess:
    def read_out(self) -> bytes:
        return b''

    def read_err(self) -> bytes:
        return b''

    def write_in(self, data: bytes):
        pass

    def close_in(self):
        pass

    def close(self) -> int:
        return 0
