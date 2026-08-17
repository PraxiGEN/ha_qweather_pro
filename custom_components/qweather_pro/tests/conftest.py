"""共享 fixtures：在真实 homeassistant 环境下运行（CI / GitHub Actions）。

pytest 的 ``homeassistant`` 插件会自动提供标准 fixtures：
``hass``、``enable_custom_integrations``、``mock_config_entry`` 等。
本文件仅补充集成特有的 ``mock_coordinator``（entity 构造所需的最小替身）。
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

    ``pytest-homeassistant-custom-component`` 不提供 ``mock_config_entry``，
    这里用 HA 自带的 ``MockConfigEntry``（含 ``entry_id``/``data``/``add_to_hass``）。
    """
    from homeassistant.config_entries import MockConfigEntry

    return MockConfigEntry(domain=DOMAIN, data={}, entry_id="test")
