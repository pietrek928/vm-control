from asyncio import StreamReader
from asyncio.subprocess import PIPE
from os import getlogin
from typing import Iterable, Tuple, Union, Optional

from asyncssh import connect, SSHClientConnectionOptions, SSHClientConnection

from gui import ConfigObject, EnField, StrField, IntField, StateChange
from session import CommandError, SessionProcess

global last_port
last_port = 22243


def next_free_port():
    # TODO: check used
    global last_port
    last_port += 1
    if last_port > 65000:
        last_port = 22243
    return last_port


class SSHProcess(SessionProcess):
    def __init__(self, chan, bufsize=-1):
        self._chan = chan
        self._stdin = chan.makefile_stdin("wb", bufsize)
        self._stdout = chan.makefile("rb", bufsize)
        self._stderr = chan.makefile_stderr("rb", bufsize)

    def read_out(self) -> bytes:
        return self._stdout.read()

    def read_err(self) -> bytes:
        return self._stderr.read()

    def write_in(self, data: bytes):
        self._stdin.write(data)

    def close_in(self):
        self._stdin.close()

    def close(self) -> int:
        return self._chan.recv_exit_status()


# class SSHSession(Session):
#     def __init__(self, host: 'SSHHost'):
#         self._ssh = connect(
#             hostname=host.host,
#             port=host.port,
#             username=host.username or None,
#             password=host.password or None,
#             options=SSHClientConnectionOptions(),
#         )
#         # TODO: pass known hosts from per-host config - security
#         # self._ssh.load_system_host_keys()
#         # self._ssh.connect(
#         #     hostname=host.host,
#         #     port=host.port,
#         #     username=host.username or None,
#         #     password=host.password or None,
#         #     compress=host.compression
#         #     # TODO: per-host private key - security
#         #     # ECDSAKey.generate(curve=SECT571R1())
#         #     # pkey =
#         # )
#         # self._transport = self._ssh.get_transport()
#
#     def execute(
#             self, cmd: str, timeout=None,
#             envs: Iterable[Tuple[str, str]] = (), bufsize=-1
#     ) -> SessionProcess:
#         chan = self._transport.open_session(timeout=timeout)
#         chan.settimeout(timeout)
#         chan.update_environment(dict(envs))
#         chan.exec_command(cmd)
#         return SSHProcess(chan, bufsize=bufsize)
#
#     def disconnect(self):
#         self._ssh.close()


class SSHHost(ConfigObject):
    host: str = StrField()
    port: int = IntField(default=22)
    username: str = StrField(default=getlogin())
    password: str = StrField(default='')
    compression: bool = EnField(default=False)

    session: Optional[SSHClientConnection] = None

    _last_port = 33354

    @property
    def next_free_port(self):
        # TODO: check used
        self._last_port += 1
        if self._last_port > 65000:
            self._last_port = 33354
        return self._last_port

    # def __init__(self):
    #     # self._session = SSHSession(SSHConfig({
    #     #     'host': '10.1.5.25',
    #     #     # 'compression': False,
    #     # }))
    #     self._session = SSHSession(SSHConfig({
    #         'host': 'elektroinf.eu',
    #         'username': 'root',
    #         # 'compression': False,
    #     }))

    def get_special_path(self, special_name) -> Optional[str]:
        if special_name == 'host':
            return '.'

    @StateChange('loaded', 'connected')
    async def connect(self):
        self.session = await connect(
            host=self.host,
            port=self.port,
            username=self.username or None,
            password=self.password or None,
            options=SSHClientConnectionOptions(
                client_version='xD',
            ),
        )

    @StateChange('connected', 'loaded')
    async def disconnect(self):
        session = self.session
        self.session = None
        session.close()
        await session.wait_closed()

    async def run_command(
            self, cmd: str, input: Union[str, bytes] = None,
            timeout=None, envs: Iterable[Tuple[str, str]] = ()
    ) -> str:
        print(cmd)
        if input:
            stdin = StreamReader()
            stdin.feed_data(input)
            stdin.feed_eof()
        else:
            stdin = PIPE
        res = await (await self.withstate('connected')).session.run(
            cmd, stdin=stdin,
            timeout=timeout, env=tuple(envs)
        )

        exit_code = res.exit_status
        if exit_code:
            raise CommandError(
                f'Command `{cmd}` failed with code {exit_code}; '
                f'stderr: {res.stderr}'
            )

        return res.stdout
