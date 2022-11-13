import hashlib
import re
from typing import Tuple, Optional

from gui import ConfigObject, StrField, PassField, StateChange
from session import CommandError


class Env(ConfigObject):
    dir: str = StrField(default='~/')
    key: str = PassField(default='')

    environment: Tuple[Tuple[str, str], ...] = ()
    _full_dir = None

    async def run_command(self, *a, **k):
        host = await self.get_host()
        return await host.run_command(*a, envs=self.environment, **k)

    def get_special_path(self, special_name) -> Optional[str]:
        if special_name == 'env':
            return '.'

    def _get_key(self) -> bytes:
        pass_bytes = ('7f34f9734bf9874' + self.key + 'b28724b8rvn9n').encode('utf-8')
        salt_bytes = '7239b974b93478nfh8734n7m884239me'.encode('utf-8')
        return hashlib.pbkdf2_hmac('sha512', pass_bytes, salt_bytes, int(2 ** 14))

    async def ensure_path(self, local_dir):
        host = await self.get_host()
        try:
            return (await host.run_command(f'realpath "{local_dir}"')).strip('\n')
        except CommandError as e:
            if ': No such file or directory\n' in str(e):
                await host.run_command(f'mkdir -p "{local_dir}"')
                return (await host.run_command(f'realpath "{local_dir}"')).strip('\n')
            else:
                raise

    @staticmethod
    def _create_keyfile_cmd(var_name):
        return (
            f'{var_name}=$(mktemp /tmp/key.XXXXXXXXXX) && '  # TODO: safer create file, ensure in ram
            f'trap "dd if=/dev/zero of=\\"${{{var_name}}}\\" status=none bs=1 count=1K ; '
            f'rm -f \\"${{{var_name}}}\\"" EXIT SIGHUP SIGKILL SIGTERM SIGINT && '
            f'( cat > "${{{var_name}}}" ) '
        )

    async def _create(self, key: bytes):
        """
        Create and encrypt directory, ensure it does not exist
        :param key:
        :return:
        """
        host = await self.get_host()
        await host.run_command(
            '( ' + self._create_keyfile_cmd('F') + (
                f'&& mkdir -p "{self._full_dir}" && rmdir "{self._full_dir}" && mkdir -p "{self._full_dir}" '
                f'&& fscrypt encrypt "{self._full_dir}" --quiet --source=raw_key --name=vm --key="$F"'
            ) + ' )',
            input=key
        )

    async def _decrypt(self, key: bytes):
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
        self._full_dir = await self.ensure_path(self.dir)
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
            f'fscrypt lock "{self._full_dir}"',
        )
