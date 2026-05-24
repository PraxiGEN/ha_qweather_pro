"""QWeather (和风天气) 配置流实现."""
from __future__ import annotations

import logging
import asyncio
import time
from typing import Any

import voluptuous as vol
import jwt
from cryptography.hazmat.primitives import serialization

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_USE_TOKEN,
    CONF_LOCATION_ID,
    CONF_HOURLYSTEPS,
    CONF_DAILYSTEPS,
    CONF_LIFEINDEX,
    CONF_UPDATE_INTERVAL,
    CONF_PROJECT_ID,
    CONF_KEY_ID,
    CONF_PRIVATE_KEY,
    CONF_ALERT,
    CONF_GIRD,
    CONF_CUSTOM_UI,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_HOST = "api.qweather.com"

class QWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """处理和风天气的配置流."""

    VERSION = 1

    def __init__(self) -> None:
        """初始化."""
        self._temp_data: dict[str, Any] = {}
        self._generated_private_key: str | None = None
        self._generated_public_key: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> QWeatherOptionsFlow:
        """获取选项流."""
        return QWeatherOptionsFlow()

    def _generate_key_pair_sync(self) -> tuple[str, str]:
        """同步生成密钥对."""
        from cryptography.hazmat.primitives.asymmetric import ed25519
        private_key = ed25519.Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return private_bytes.decode('utf-8'), public_bytes.decode('utf-8')

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """初始配置步骤."""
        if user_input is not None:
            self._temp_data = user_input
            if user_input.get(CONF_USE_TOKEN):
                return await self.async_step_jwt_setup()
            return await self._async_verify_and_create(user_input)

        # 默认位置根据 HA 系统坐标生成
        default_location = f"{round(self.hass.config.longitude, 2)},{round(self.hass.config.latitude, 2)}"
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=DEFAULT_HOST): selector.TextSelector(),
                vol.Required(CONF_LOCATION_ID, default=default_location): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        autocomplete="address-level2"
                   )
                ),                                       
                vol.Required(CONF_USE_TOKEN, default=False): selector.BooleanSelector(),
                vol.Optional(CONF_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }),
            description_placeholders={
                "location_hint": "格式：经度,纬度 (如 116.41,39.92) 或 城市ID"
            }
        )
    async def async_step_jwt_setup(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """处理 JWT 认证步骤."""
        if not self._generated_private_key:
            self._generated_private_key, self._generated_public_key = await self.hass.async_add_executor_job(
                self._generate_key_pair_sync
            )

        if user_input is not None:
            config_data = {
                **self._temp_data, 
                **user_input, 
                CONF_PRIVATE_KEY: self._generated_private_key
            }
            return await self._async_verify_and_create(config_data)

        return self.async_show_form(
            step_id="jwt_setup",
            data_schema=vol.Schema({
                vol.Required(CONF_PROJECT_ID): selector.TextSelector(),
                vol.Required(CONF_KEY_ID): selector.TextSelector(),
            }),
            description_placeholders={"public_key": self._generated_public_key}
        )

    async def _async_verify_and_create(self, config_data: dict[str, Any]) -> FlowResult:
        """核心验证并自动获取城市名标题."""
        errors: dict[str, str] = {}
        session = async_get_clientsession(self.hass)
        
        normalized_location = config_data[CONF_LOCATION_ID].replace(" ", "")
        config_data[CONF_LOCATION_ID] = normalized_location 
        
        city_title = "和风天气"
        headers = {}

        # 1. 认证检查
        if config_data.get(CONF_USE_TOKEN):
            try:
                private_key_obj = serialization.load_pem_private_key(
                    config_data[CONF_PRIVATE_KEY].encode('utf-8'),
                    password=None
                )
                now_ts = int(time.time())
                payload = {'iat': now_ts - 30, 'exp': now_ts + 3600, 'sub': config_data[CONF_PROJECT_ID]}
                token = jwt.encode(payload, private_key_obj, algorithm='EdDSA', headers={'kid': config_data[CONF_KEY_ID]})
                headers["Authorization"] = f"Bearer {token}"
            except Exception:
                errors["base"] = "jwt_error"
        else:
            if not config_data.get(CONF_API_KEY):
                errors["base"] = "api_key_missing"

        # 2. 访问 GeoAPI 获取城市名称并验证合法性
        if not errors:
            try:
                params = {"location": normalized_location}
                if not config_data.get(CONF_USE_TOKEN):
                    params["key"] = config_data[CONF_API_KEY]

                async with asyncio.timeout(10):
                    resp = await session.get("https://geoapi.qweather.com/v2/city/lookup", params=params, headers=headers)
                    res = await resp.json()
                    if res.get("code") == "200" and res.get("location"):
                        # 成功获取真实的城市名称
                        city_title = res["location"][0]["name"]
                    else:
                        errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"

        if errors:
            # 根据认证方式返回对应的表单
            step = "jwt_setup" if config_data.get(CONF_USE_TOKEN) else "user"
            return self.async_show_form(step_id=step, data_schema=self._get_schema(config_data), errors=errors)

        # 3. 设置唯一 ID (基于位置，防止重复添加)
        unique_id = f"qw_{normalized_location.replace(',', '_')}"
        await self.async_set_unique_id(unique_id)
        
        if self.source == config_entries.SOURCE_RECONFIGURE:
            return self.async_update_reload_and_abort(self._get_reconfigure_entry(), data=config_data)
        
        self._abort_if_unique_id_configured()

        # 4. 关键：以城市名作为标题创建集成，无需在 __init__.py 重命名
        return self.async_create_entry(title=city_title, data=config_data)

    def _get_schema(self, data: dict) -> vol.Schema:
        """根据输入返回对应的 Schema 用于错误回显."""
        if data.get(CONF_USE_TOKEN):
            return vol.Schema({
                vol.Required(CONF_PROJECT_ID, default=data.get(CONF_PROJECT_ID)): selector.TextSelector(),
                vol.Required(CONF_KEY_ID, default=data.get(CONF_KEY_ID)): selector.TextSelector(),
            })
        return vol.Schema({
            vol.Required(CONF_HOST, default=data.get(CONF_HOST)): selector.TextSelector(),
            vol.Required(CONF_LOCATION_ID, default=data.get(CONF_LOCATION_ID)): selector.TextSelector(),
            vol.Required(CONF_USE_TOKEN, default=data.get(CONF_USE_TOKEN)): selector.BooleanSelector(),
            vol.Optional(CONF_API_KEY, default=data.get(CONF_API_KEY)): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        })

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """处理重新配置."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            return await self._async_verify_and_create({**entry.data, **user_input})

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY, default=entry.data.get(CONF_API_KEY, "")): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            })
        )

class QWeatherOptionsFlow(config_entries.OptionsFlow):
    """处理选项配置."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            # 在这里保存时，由于 Selector 选出来的是字符串，
            # 建议直接保存，coordinator 里的 _to_f 函数会自动处理转换
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        data = self.config_entry.data

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                # 1. 刷新间隔
                vol.Required(
                    CONF_UPDATE_INTERVAL, 
                    default=options.get(CONF_UPDATE_INTERVAL, 15)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=1440, step=1, mode=selector.NumberSelectorMode.BOX)
                ),
                # 2. 每日预报天数
                vol.Required(
                    CONF_DAILYSTEPS, 
                    default=str(options.get(CONF_DAILYSTEPS, 7))
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["3", "7", "10", "15"],
                        mode=selector.SelectSelectorMode.DROPDOWN
                    )
                ),
                # 3. 逐小时预报时长 
                vol.Required(
                    CONF_HOURLYSTEPS, 
                    default=str(options.get(CONF_HOURLYSTEPS, 24))
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["24", "72", "168"],
                        mode=selector.SelectSelectorMode.DROPDOWN
                    )
                ),
                # 4. 功能开关
                vol.Required(CONF_ALERT, default=options.get(CONF_ALERT, True)): selector.BooleanSelector(),
                vol.Required(CONF_LIFEINDEX, default=options.get(CONF_LIFEINDEX, True)): selector.BooleanSelector(),
                vol.Required(CONF_GIRD, default=options.get(CONF_GIRD, False)): selector.BooleanSelector(),
                vol.Required(CONF_CUSTOM_UI, default=options.get(CONF_CUSTOM_UI, False)): selector.BooleanSelector(),
            }),
        )