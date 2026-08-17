"""共享 fixtures：在真实 homeassistant 环境下运行（CI / GitHub Actions）。

pytest 的 ``homeassistant`` 插件会自动提供标准 fixtures（``hass``、
``enable_custom_integrations`` 等）。本文件补充集成特有的 ``mock_coordinator``
与 ``mock_config_entry`` 两个 fixture。``MockConfigEntry`` 来自
``pytest_homeassistant_custom_component.common``（自定义组件测试的标准来源）。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.qweather_pro.const import DOMAIN


@pytest.fixture
def mock_coordinator():
    """最小 coordinator 替身：提供 entity 构造所需的 ``data`` / ``device_info``。

    测试内通常再覆盖 ``mock_coordinator.data = <测试数据>``。
    """
    coord = MagicMock()
    coord.data = {}
    coord.device_info = {"identifiers": {(DOMAIN, "test")}}
    return coord


@pytest.fixture
def mock_config_entry():
    """提供实体/入口测试所需的 config entry 替身。

    自定义组件测试应从 ``pytest_homeassistant_custom_component.common`` 导入
    ``MockConfigEntry``（CI 装的 pytest-homeassistant-custom-component 提供；
    该版本 homeassistant 的 ``homeassistant.config_entries`` 已不再导出它）。
    """
    try:
        from pytest_homeassistant_custom_component.common import MockConfigEntry
    except Exception:  # pragma: no cover - 旧版回退
        from homeassistant.config_entries import MockConfigEntry  # type: ignore

    return MockConfigEntry(domain=DOMAIN, data={}, entry_id="test")
