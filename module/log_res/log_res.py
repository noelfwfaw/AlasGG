from cached_property import cached_property
from module.logger import logger
import module.config.utils as utils
from datetime import datetime

# 如果 utils 模块中没有 deep_get 和 deep_set，则动态定义并注入
if not (hasattr(utils, 'deep_get') and hasattr(utils, 'deep_set')):
    def deep_get(d, keys, default=None):
        """
        递归安全地获取嵌套字典的值
        """
        if isinstance(keys, str):
            keys = keys.split('.')
        assert isinstance(keys, list)
        if d is None:
            return default
        if not keys:
            return d
        return deep_get(d.get(keys[0]), keys[1:], default)

    def deep_set(d, keys, value):
        """
        递归安全地设置嵌套字典的值
        """
        if isinstance(keys, str):
            keys = keys.split('.')
        assert isinstance(keys, list)
        if not keys:
            return value
        if not isinstance(d, dict):
            d = {}
        d[keys[0]] = deep_set(d.get(keys[0], {}), keys[1:], value)
        return d

    # 将定义好的函数添加到 utils 模块中
    utils.deep_get = deep_get
    utils.deep_set = deep_set

# 然后再从 utils 模块导入 deep_get 和 deep_set
from module.config.utils import deep_get, deep_set

class LogRes:
    """
    set attr--->
    Logres(AzurLaneConfig).<res_name>=resource_value:int
    OR  ={'Value:int, 'Limit/Total':int}:dict
    """
    YellowCoin: list

    def __init__(self, config):
        self.__dict__['config'] = config

    def __setattr__(self, key, value):
        if key in self.groups:
            _key_group = f'Dashboard.{key}'
            _mod = False
            original = deep_get(self.config.data, keys=_key_group)
            if isinstance(value, int):
                if original['Value'] != value:
                    _key = _key_group + '.Value'
                    self.config.modified[_key] = value
                    _time = datetime.now().replace(microsecond=0)
                    _key_time = _key_group + f'.Record'
                    self.config.modified[_key_time] = _time
            elif isinstance(value, dict):
                for value_name, _value in value.items():
                    if _value == original[value_name]:
                        continue
                    _key = _key_group + f'.{value_name}'
                    self.config.modified[_key] = _value
                    _key_time = _key_group + f'.Record'
                    _time = datetime.now().replace(microsecond=0)
                    self.config.modified[_key_time] = _time
        else:
            logger.info('No such resource on dashboard')
            super().__setattr__(name=key, value=value)

    @cached_property
    def groups(self) -> dict:
        from module.config.utils import read_file, filepath_argument
        return deep_get(d=read_file(filepath_argument("dashboard")), keys='Dashboard')

    """
    def log_res(self, name, modified: dict, update=True):
        if name in self.groups:
            key = f'Dashboard.{name}'
            original = deep_get(self.config.data, keys=key)
            _mod = False
            for value_name, value in modified.items():
                if value == original[value_name]:
                    continue
                _key = key + f'.{value_name}'
                self.config.modified[_key] = value
                _mod = True
            if _mod:
                _key_time = key + f'.Record'
                _time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.config.modified[_key_time] = _time
                if update:
                    self.config.update()
        else:
            logger.warning('No such resource!')
        return True
        """


if __name__ == '__main__':
    from module.config.config import AzurLaneConfig
    config = AzurLaneConfig('alas2')
    LogRes(config=config).ActionPoint = {'Total': 99999, 'Value': 99999}
    config.update()
    exit(0)

