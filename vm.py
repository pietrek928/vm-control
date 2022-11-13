from typing import Optional

from gui import ConfigObject, StrField, IntField, FloatField, SelectField, EnField, StateChange
from host import SSHProcess


class ShellCommand:
    def __init__(self, cmd=''):
        self.cmd = cmd

    def a(self, n, v=None):
        if v is not None:
            self.cmd += f' -{n} "{v}"'
        else:
            self.cmd += f' -{n}'
        return self

    def __str__(self):
        return self.cmd


class QemuVM(ConfigObject):
    dir: str = StrField(default='.')
    name: str = StrField(default='test')
    arch: str = SelectField(values=('x86_64',))
    cpu: str = SelectField(values=('host',))
    smp: int = IntField(default=4)
    vga: int = StrField(default='virtio')
    ram_mb: float = FloatField(default=1024.)
    net: str = SelectField(values=('none',))
    virtio: bool = EnField(default=True)
    drives: str = StrField(default='')

    def __init__(self, current_path: str, loader: 'ObjectLoader', data):
        super().__init__(current_path, loader, data)
        self._process: Optional[SSHProcess] = None

    @StateChange('loaded', 'started')
    async def start(self):
        cmd = ShellCommand(f'qemu-system-{self.arch}') \
            .a('name', self.name) \
            .a('enable-kvm') \
            .a('machine', 'type=pc,accel=kvm') \
            .a('smp', self.smp) \
            .a('vga', self.vga) \
            .a('m', f'{self.ram_mb}M') \
            .a('usb') \
            .a('device', 'usb-tablet')
        if self.virtio:
            cmd.a('device', 'virtio-scsi-pci')
        for d in self.drives.split(','):
            d = d.strip()
            if d:
                cmd.a('drive', (await self.o(d).withstate('created')).get_mount_params())
        # process ?
        await self.o('$env').run_command(cmd.cmd)


class DriveImage(ConfigObject):
    path: str = StrField()
    base_img_path: str = StrField()
    size_mb: float = FloatField(default=1024.)
    mode: str = SelectField(values=('drive', 'cdrom-ro',))
    format: str = SelectField(values=('iso-ro', 'qcow2',))

    @StateChange('loaded', 'created')
    async def create(self):
        if self.format == 'qcow2':
            cmd = f'( ls "{self.path}" || qemu-img create -f qcow2 '
            if self.base_img_path:
                cmd += f'-o backing_file="{self.base_img_path}" "{self.path}"'
            else:
                cmd += f'"{self.path}" {self.size_mb / 1024.}G'
            cmd += ' )'
        else:
            cmd = f'ls "{self.path}"'
        await self.o('$env').run_command(cmd)

    @StateChange('created', 'loaded')
    async def remove(self):
        await self.o('$env').run_command(f'rm -f {self.path}')

    def get_mount_params(self):
        if self.mode == 'cdrom-r':
            return f'file={self.path},media=cdrom,readonly'
        elif self.mode == 'drive':
            return f'file={self.path},format={self.format},if=virtio,discard=unmap,detect-zeroes=unmap'
