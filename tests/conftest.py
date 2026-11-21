"""共享 fixtures：mock_coordinator / mock_config_entry。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.qweather_pro.const import DOMAIN

@pytest.fixture
def mock_coordinator():
    """最小 coordinator 替身（data / device_info 供实体构造）."""
    coord = MagicMock()
    coord.data = {}
    coord.device_info = {"identifiers": {(DOMAIN, "test")}}
    return coord

@pytest.fixture
def mock_config_entry():
    """config entry 替身（MockConfigEntry 取自 pytest_homeassistant_custom_component）."""
    try:
        from pytest_homeassistant_custom_component.common import MockConfigEntry
    except Exception:  # pragma: no cover - 旧版回退
        from homeassistant.config_entries import MockConfigEntry  # type: ignore

    return MockConfigEntry(domain=DOMAIN, data={}, entry_id="test")

def add_location_subentry(hass, entry, coords="120,30", title="测试城市"):
    """为条目挂一个 location 子条目（v1.3.0 起 1 条目 = 1 账号 + N 位置）。"""
    from homeassistant.config_entries import ConfigSubentry

    from custom_components.qweather_pro.const import (
        CONF_LOCATION_ID,
        SUBENTRY_TYPE_LOCATION,
    )

    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            subentry_type=SUBENTRY_TYPE_LOCATION,
            title=title,
            data={CONF_LOCATION_ID: coords},
            unique_id=f"qw_{coords.replace(',', '_')}",
        ),
    )
