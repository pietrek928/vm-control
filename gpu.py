from lxml import etree as ET

from gui import ConfigObject, FloatField, StrField


class GPU(ConfigObject):
    name = StrField(default='')
    model = StrField(default='')
    ram_mb = FloatField(default=0)


class GPUS(ConfigObject):
    properties: str = None

    async def detect_gpus(self):
        host = await self.get_host()
        xml_gpus = await host.run_command('nvidia-smi -q -x')
        self.properties = xml_gpus

        root = ET.fromstring(xml_gpus)
        for gpu in root.xpath('/nvidia_smi_log/gpu'):
            gpu_obj = GPU(self._current_path, self._loader, dict(
                name=gpu.get('id'),
                model=gpu.xpath('./product_name')[0].text,
                ram_mb=float(gpu.xpath('./fb_memory_usage/total')[0].text.split(' ')[0]),
            ))
            self._loader._loaded[f'{self._current_path}/{gpu_obj.name}'] = gpu_obj
