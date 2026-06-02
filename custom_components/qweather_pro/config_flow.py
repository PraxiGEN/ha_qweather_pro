"""QWeather (和风天气) 配置流实现 ."""
from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .api import QWeatherAPI
from .const import (
    DOMAIN,
    CONF_USE_TOKEN,
    CONF_LOCATION_ID,
    CONF_HOURLYSTEPS,
    CONF_DAILYSTEPS,
    CONF_UPDATE_INTERVAL,
    CONF_PROJECT_ID,
    CONF_KEY_ID,
    CONF_PRIVATE_KEY,
    CONF_GIRD,
    CONF_CUSTOM_UI,
    MANUFACTURER,
    DEFAULT_UPDATE_INTERVAL,
    LANGUAGE_MAP,
    LOGGER,
    
)

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

        default_location = f"{round(self.hass.config.longitude, 2)},{round(self.hass.config.latitude, 2)}"
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): selector.TextSelector(),
                vol.Required(CONF_LOCATION_ID, default=default_location): selector.TextSelector(),                                       
                vol.Required(CONF_USE_TOKEN, default=False): selector.BooleanSelector(),
                vol.Optional(CONF_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }),
        )

    async def async_step_jwt_setup(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """JWT 身份验证步骤."""
        if not self._generated_private_key:
            self._generated_private_key, self._generated_public_key = await self.hass.async_add_executor_job(
                self._generate_key_pair_sync
            )

        if user_input is not None:
            config_data = {**self._temp_data, **user_input, CONF_PRIVATE_KEY: self._generated_private_key}
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
        """核心验证逻辑：实现地理数据标准化，强制转换为标准经纬度存储."""
        errors: dict[str, str] = {}
        session = async_get_clientsession(self.hass)

        ha_lang = self.hass.config.language
        qweather_lang = LANGUAGE_MAP.get(ha_lang, "en")        
        
        user_host = config_data[CONF_HOST].strip()
        config_data[CONF_HOST] = user_host
        raw_loc = config_data[CONF_LOCATION_ID].strip()

        deprecated_domains = ["api.qweather.com", "devapi.qweather.com", "geoapi.qweather.com"]
        if any(domain in user_host for domain in deprecated_domains):
            errors["base"] = "api_host_deprecated"

        city_title = MANUFACTURER
        normalized_coords = ""
        
        # 准备 API 实例进行位置验证与标准化
        if not errors:
            api = QWeatherAPI(
                session=session,
                api_key=config_data.get(CONF_API_KEY),
                use_token=config_data.get(CONF_USE_TOKEN),
                project_id=config_data.get(CONF_PROJECT_ID),
                key_id=config_data.get(CONF_KEY_ID),
                private_key=config_data.get(CONF_PRIVATE_KEY),
                host=user_host
            )

            try:
                # 调用城市搜索，支持模糊名称、ID、坐标
                res = await api.city_lookup(raw_loc, lang=qweather_lang)
                
                if res.get("code") == "200" and res.get("location"):
                    location_info = res["location"][0]
                    
                    # --- 地理数据标准化核心 (Normalization) ---
                    # 无论输入是什么，统一提取 API 返回的高精度经纬度
                    # 和风 API 要求：经度在前，纬度在后，建议保留 2 位小数
                    std_lon = round(float(location_info["lon"]), 2)
                    std_lat = round(float(location_info["lat"]), 2)
                    
                    normalized_coords = f"{std_lon},{std_lat}"
                    city_title = location_info["name"]
                    
                    # 将存储的位置信息强制覆盖为标准坐标，供后续所有端点使用
                    config_data[CONF_LOCATION_ID] = normalized_coords
                    # ----------------------------------------
                else:
                    errors["base"] = "location_not_found"
            except Exception as err:
                LOGGER.error("无法连接至 API Host %s: %s", user_host, err)
                errors["base"] = "cannot_connect"

        # 错误处理回显
        if errors:
            step = "jwt_setup" if config_data.get(CONF_USE_TOKEN) else "user"
            return self.async_show_form(step_id=step, data_schema=self._get_schema(config_data), errors=errors)

        # 锁定物理唯一 ID (基于标准坐标，防止不同输入模式导致的重复添加)
        unique_id = f"qw_{normalized_coords.replace(',', '_')}"
        await self.async_set_unique_id(unique_id)
        
        # 处理重新配置流程
        if self.source == config_entries.SOURCE_RECONFIGURE:
            return self.async_update_reload_and_abort(self._get_reconfigure_entry(), data=config_data)
        
        self._abort_if_unique_id_configured()

        # 创建集成条目并注入默认选项
        return self.async_create_entry(
            title=city_title, 
            data=config_data,
            options={
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_DAILYSTEPS: "7",
                CONF_HOURLYSTEPS: "24",
                CONF_GIRD: False,
                CONF_CUSTOM_UI: False,
            }
        )

    def _get_schema(self, data: dict) -> vol.Schema:
        """获取带有当前数据的 Schema 用于回显."""
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
        """重新配置逻辑."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            return await self._async_verify_and_create({**entry.data, **user_input})

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST, "")): selector.TextSelector(),
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
                    default=options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=1440, step=1, mode=selector.NumberSelectorMode.BOX)
                ),
                # 2. 每日预报天数 (使用标准字符串选项解决 expected str 错误)
                vol.Required(
                    CONF_DAILYSTEPS, 
                    default=str(options.get(CONF_DAILYSTEPS, 7))
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["3", "7", "10", "15", "30"],
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
                vol.Required(CONF_GIRD, default=options.get(CONF_GIRD, False)): selector.BooleanSelector(),
                vol.Required(CONF_CUSTOM_UI, default=options.get(CONF_CUSTOM_UI, False)): selector.BooleanSelector(),
            }),
        )