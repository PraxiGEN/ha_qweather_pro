"""QWeather (和风天气) 配置流实现 ."""
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
    LOGGER,
)

DEFAULT_HOST = "api.qweather.com"

class QWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """处理和风天气的配置流."""

    VERSION = 1

    def __init__(self) -> None:
        """初始化临时变量."""
        self._temp_data: dict[str, Any] = {}
        self._generated_private_key: str | None = None
        self._generated_public_key: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> QWeatherOptionsFlow:
        """获取并关联选项流."""
        return QWeatherOptionsFlow()

    def _generate_key_pair_sync(self) -> tuple[str, str]:
        """同步生成 JWT 密钥对."""
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
        """用户首次手动添加集成的步骤."""
        if user_input is not None:
            self._temp_data = user_input
            if user_input.get(CONF_USE_TOKEN):
                return await self.async_step_jwt_setup()
            return await self._async_verify_and_create(user_input)

        # 默认使用 HA 系统配置的坐标
        default_location = f"{round(self.hass.config.longitude, 2)},{round(self.hass.config.latitude, 2)}"
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=DEFAULT_HOST): selector.TextSelector(),
                vol.Required(CONF_LOCATION_ID, default=default_location): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
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
        """JWT 身份验证的高级设置步骤."""
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
        """核心逻辑：验证凭据、抓取城市标题、并创建条目."""
        errors: dict[str, str] = {}
        session = async_get_clientsession(self.hass)
        
        # 统一位置 ID 格式
        loc = config_data[CONF_LOCATION_ID].replace(" ", "")
        config_data[CONF_LOCATION_ID] = loc 
        
        city_title = "和风天气"
        headers = {}

        # 1. 预校验认证格式
        if config_data.get(CONF_USE_TOKEN):
            try:
                private_key_obj = serialization.load_pem_private_key(
                    config_data[CONF_PRIVATE_KEY].encode('utf-8'), password=None
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

        # 2. 访问 GeoAPI 获取真实的城市名称标题
        if not errors:
            try:
                params = {"location": loc, "range": "cn"}
                if not config_data.get(CONF_USE_TOKEN):
                    params["key"] = config_data[CONF_API_KEY]

                async with asyncio.timeout(10):
                    resp = await session.get("https://geoapi.qweather.com/v2/city/lookup", params=params, headers=headers)
                    res = await resp.json()
                    if res.get("code") == "200" and res.get("location"):
                        # 核心点：获取城市名
                        city_title = res["location"][0]["name"]
                    else:
                        errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"

        # 3. 处理错误回显
        if errors:
            step = "jwt_setup" if config_data.get(CONF_USE_TOKEN) else "user"
            return self.async_show_form(step_id=step, data_schema=self._get_schema(config_data), errors=errors)

        # 4. 设置唯一 ID (防止同一个位置添加两次)
        unique_id = f"qw_{loc.replace(',', '_')}"
        await self.async_set_unique_id(unique_id)
        
        # 处理“重新配置”流程
        if self.source == config_entries.SOURCE_RECONFIGURE:
            return self.async_update_reload_and_abort(self._get_reconfigure_entry(), data=config_data)
        
        self._abort_if_unique_id_configured()

        # 5. 【核心修复】创建条目并注入默认选项
        return self.async_create_entry(
            title=city_title, 
            data=config_data,
            options={
                CONF_UPDATE_INTERVAL: 15,
                CONF_DAILYSTEPS: "7",
                CONF_HOURLYSTEPS: "24",
                CONF_ALERT: True,
                CONF_LIFEINDEX: True,
                CONF_GIRD: False,
                CONF_CUSTOM_UI: False,
            }
        )

    def _get_schema(self, data: dict) -> vol.Schema:
        """辅助函数：根据当前认证模式返回对应的表单结构."""
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
        """处理集成卡片‘三点’菜单中的重新配置请求."""
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
    """处理已安装集成的 UI 选项配置."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """选项配置主界面."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options

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
                # 2. 每日预报天数 (使用标准字符串选项解决 expected str 错误)
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
                # 4. 开关项
                vol.Required(CONF_ALERT, default=options.get(CONF_ALERT, True)): selector.BooleanSelector(),
                vol.Required(CONF_LIFEINDEX, default=options.get(CONF_LIFEINDEX, True)): selector.BooleanSelector(),
                vol.Required(CONF_GIRD, default=options.get(CONF_GIRD, False)): selector.BooleanSelector(),
                vol.Required(CONF_CUSTOM_UI, default=options.get(CONF_CUSTOM_UI, False)): selector.BooleanSelector(),
            }),
        )