import hashlib
import re
from asyncio import create_task, wait, FIRST_COMPLETED
from os import SEEK_END
from os.path import dirname
from time import perf_counter
from typing import Tuple, Optional, Iterable, AnyStr

import aiofiles
from aiofiles.threadpool.binary import AsyncBufferedReader
from asyncssh import SSHClientProcess

from gui import ConfigObject, StrField, PassField, StateChange, decode_data
from session import CommandError
from task_manager import Task, run_task


def _format_speed(bps: float):
    if bps < 1024.:
        return f'{bps:.1f} B/s'
    bps /= 1024.
    if bps < 1024.:
        return f'{bps:.1f} KB/s'
    bps /= 1024.
    return f'{bps:.1f} MB/s'


def _format_seconds(secs: float):
    secs = int(secs)
    tm = f'{secs % 60:02}s'
    secs //= 60
    if not secs:
        return tm
    tm = f'{secs % 60:02}:' + tm
    secs //= 60
    if not secs:
        return tm
    tm = f'{secs}:' + tm
    return tm


class Env(ConfigObject):
    dir: str = StrField(default='~/')
    key: str = PassField(default='')

    environment: Tuple[Tuple[str, str], ...] = ()
    _full_dir = None

    def format_path(self, d: Optional[str] = None):
        if not self._full_dir:
            return d
        if not d:
            return self._full_dir
        if d.startswith('/'):
            return d
        else:
            return f'{self._full_dir}/{d}'

    async def run_command(self, *a, **k):
        # TODO: set path ?
        host = await self.get_host()
        return await host.run_command(*a, envs=self.environment, **k)

    async def monitor_process(self, process: SSHClientProcess, task: Task):
        try:
            while True:
                done, pending = await wait((
                    create_task(process.stdout.read()),
                    create_task(process.stderr.read()),
                ), return_when=FIRST_COMPLETED)
                if len(done):
                    data_line = await done.pop()
                    task.set_message(decode_data(data_line))
                for p in pending:
                    p.cancel()
        finally:
            process.terminate()

    async def start_process(
            self, cmd: str, input: Optional[AnyStr] = None,
            envs: Iterable[Tuple[str, str]] = ()
    ):
        host = await self.get_host()
        process = await (await host.withstate('connected')).session.create_process(
            cmd, input=input, env=envs
        )
        task = Task(cmd)
        run_task(self.monitor_process(process, task), task)

    async def upload_file_content(
            self, process: SSHClientProcess, task: Task,
            fp_in: AsyncBufferedReader, upload_count: int,
            chunk_size=int(2 ** 16)
    ):
        start_time = perf_counter()
        start_upload_count = upload_count
        last_meas = perf_counter()
        last_upload_count = upload_count

        try:
            stdin = process.stdin

            while upload_count:
                data = await fp_in.read(min(upload_count, chunk_size))
                await stdin.drain()
                task.set_progress(1. - upload_count / start_upload_count)
                new_meas = perf_counter()
                if new_meas - last_meas > 20.:
                    current_speed = (last_upload_count - upload_count) / (new_meas - last_meas)
                    overall_speed = (start_upload_count - upload_count) / (new_meas - start_time)
                    task.set_message(
                        f'Current speed: {_format_speed(current_speed)}'
                        f'({_format_seconds(upload_count / current_speed)} elapsed) '
                        f'Overall speed: {_format_speed(overall_speed)}'
                        f'({_format_seconds(upload_count / overall_speed)} elapsed)'
                    )
                    last_meas = new_meas
                    last_upload_count = upload_count
                upload_count -= len(data)
                stdin.write(data)
            stdin.write_eof()
            await stdin.drain()
            task.set_progress(1.)
        except BrokenPipeError:
            print('Connection failed')
        finally:
            try:
                await fp_in.close()
            except Exception as e:
                print('Closing file failed', e)
            completed = await process.wait(timeout=5.)
            process.terminate()
            print(
                'Process exit code', completed.returncode, 'output:',
                decode_data(await process.stderr.read()),
                decode_data(await process.stdout.read()),
            )

    async def upload_file(self, local_fname: str, dst_fname: str):
        await self.ensure_file_path(dst_fname)

        fp_in = await aiofiles.open(local_fname, mode='rb')
        await fp_in.seek(0, SEEK_END)
        upload_size = await fp_in.tell()
        await fp_in.seek(0)

        cmd = f'cat > "{self.format_path(dst_fname)}"'
        host = await self.get_host()
        process = await (await host.withstate('connected')).session.create_process(
            cmd, env=self.environment
        )

        task = Task(f'{local_fname} -> {dst_fname}', progress=True)
        run_task(self.upload_file_content(
            process, task, fp_in, upload_size
        ), task)

    def get_special_path(self, special_name) -> Optional[str]:
        if special_name == 'env':
            return '.'

    def _get_key(self) -> bytes:
        pass_bytes = ('7f34f9734bf9874' + self.key + 'b28724b8rvn9n').encode('utf-8')
        salt_bytes = '7239b974b93478nfh8734n7m884239me'.encode('utf-8')
        return hashlib.pbkdf2_hmac('sha512', pass_bytes, salt_bytes, int(2 ** 14))

    async def ensure_path(self, local_dir):
        local_dir = self.format_path(local_dir)
        host = await self.get_host()
        try:
            await host.run_command(f'ls "{local_dir}"')
            return (await host.run_command(f'realpath "{local_dir}"')).strip('\n')
        except CommandError as e:
            if ': No such file or directory\n' in str(e):
                await host.run_command(f'mkdir -p "{local_dir}"')
                return (await host.run_command(f'realpath "{local_dir}"')).strip('\n')
            else:
                raise

    async def ensure_file_path(self, fname):
        dir_name = dirname(fname)
        if not dir_name:
            return

        await self.ensure_path(dir_name)

    @staticmethod
    def _create_keyfile_cmd(var_name):
        return (
            f'{var_name}=$(mktemp /tmp/key.XXXXXXXXXX)'  # TODO: safer create file, ensure in ram
            f' && trap "dd if=/dev/zero of=\\"${{{var_name}}}\\" status=none bs=1 count=1K ; '
            f'rm -f \\"${{{var_name}}}\\"" EXIT SIGHUP SIGKILL SIGTERM SIGINT'
            f' && ( cat > "${{{var_name}}}" ) '
        )

    async def _create(self, key: bytes):
        """
        Create and encrypt directory, ensure it does not exist
        :param key:
        :return:
        """
        self._full_dir = None
        self._full_dir = await self.ensure_path(self.dir)
        host = await self.get_host()
        await host.run_command(
            '( ' + self._create_keyfile_cmd('F') + (
                f'&& mkdir -p "{self._full_dir}" && rmdir "{self._full_dir}" && mkdir -p "{self._full_dir}" '
                f'&& fscrypt encrypt "{self._full_dir}" --quiet --source=raw_key --name=vm --key="$F"'
            ) + ' )',
            input=key
        )

    async def _decrypt(self, key: bytes):
        self._full_dir = None
        self._full_dir = await self.ensure_path(self.dir)
        host = await self.get_host()
        await host.run_command(
            '( ' + self._create_keyfile_cmd('F') + (
                f'&& ls "{self._full_dir}" '
                f'&& fscrypt unlock "{self._full_dir}" --key="$F"'
            ) + ' )',
            input=key
        )

    @StateChange('loaded', 'unlocked')
    async def unlock(self):
        try:
            await self._decrypt(self._get_key()[:32])
        except CommandError as e:
            err_str = re.sub(r'\s+', ' ', str(e))
            if ': this file or directory is already unlocked' in err_str:
                return
            elif ': No such file or directory' in err_str:
                await self._create(self._get_key()[:32])
            else:
                raise

    @StateChange('unlocked', 'loaded')
    async def lock(self):
        host = await self.get_host()
        await host.run_command(
            f'fscrypt lock --drop-caches=false "{self._full_dir}"',
        )
