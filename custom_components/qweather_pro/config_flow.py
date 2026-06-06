"""QWeather (和风天气) 配置流实现."""
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
    CONF_ACCOUNT_SELECT,
    CONF_KEY_ID,
    CONF_PRIVATE_KEY,
    CONF_GIRD,
    CONF_CUSTOM_UI,
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
        self._discovered_locations: list[dict[str, Any]] = []
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
        """入口步骤：决定是新建还是复用账号."""
        existing_entries = self._async_current_entries()
        
        # 如果是第一次添加，直接走新建流程
        if not existing_entries:
            return await self.async_step_setup(user_input)

        # 如果已存在实例，显示“引导页”
        if user_input is not None:
            selection = user_input.get(CONF_ACCOUNT_SELECT)
            if selection == "new_account":
                return await self.async_step_setup()
            
            # 【复用逻辑】记住选中的 entry_id
            self._temp_data["reuse_from"] = selection
            return await self.async_step_reuse_location()

        # 构造“复用或新建”的选择列表
        account_options = [{"value": "new_account", "label": "Add New Account"}]
        for entry in existing_entries:
            # 标签直接显示为：复用 [城市名] 的账号
            account_options.append({"value": entry.entry_id, "label": entry.title})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ACCOUNT_SELECT, default="new_account"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=account_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="account_selection"
                    )
                )
            })
        )

    async def async_step_setup(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """标准设置页面."""
        if user_input is not None:
            self._temp_data.update(user_input)
            if user_input.get(CONF_USE_TOKEN):
                return await self.async_step_jwt_setup()
            return await self._async_search_location(self._temp_data)

        default_location = f"{round(self.hass.config.longitude, 2)},{round(self.hass.config.latitude, 2)}"
        return self.async_show_form(
            step_id="setup",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): selector.TextSelector(),
                vol.Required(CONF_LOCATION_ID, default=default_location): selector.TextSelector(),                                       
                vol.Required(CONF_USE_TOKEN, default=False): selector.BooleanSelector(),
                vol.Optional(CONF_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }),
        )

    async def async_step_reuse_location(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """复用模式下的精简表单：只显示原有的位置输入框."""
        if user_input is not None:
            # 从选中的旧条目中提取认证信息
            reuse_id = self._temp_data["reuse_from"]
            old_entry = next(e for e in self._async_current_entries() if e.entry_id == reuse_id)
            
            # 合并凭据到临时数据
            self._temp_data.update(old_entry.data)
            self._temp_data[CONF_LOCATION_ID] = user_input[CONF_LOCATION_ID]
            
            return await self._async_search_location(self._temp_data)

        # 沿用原有的位置输入框定义
        return self.async_show_form(
            step_id="reuse_location",
            data_schema=vol.Schema({
                vol.Required(CONF_LOCATION_ID): selector.TextSelector(),
            })
        )

    async def async_step_jwt_setup(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """JWT 身份验证步骤."""
        if not self._generated_private_key:
            self._generated_private_key, self._generated_public_key = await self.hass.async_add_executor_job(
                self._generate_key_pair_sync
            )

        if user_input is not None:
            self._temp_data.update({
                **user_input, 
                CONF_PRIVATE_KEY: self._generated_private_key
            })
            return await self._async_search_location(self._temp_data)

        return self.async_show_form(
            step_id="jwt_setup",
            data_schema=vol.Schema({
                vol.Required(CONF_PROJECT_ID): selector.TextSelector(),
                vol.Required(CONF_KEY_ID): selector.TextSelector(),
            }),
            description_placeholders={"public_key": self._generated_public_key}
        )

    async def _async_search_location(self, config_data: dict[str, Any]) -> FlowResult:
        """核心搜索逻辑：验证 Host 并抓取城市候选项."""
        errors: dict[str, str] = {}
        session = async_get_clientsession(self.hass)
        
        user_host = config_data[CONF_HOST].strip()
        raw_loc = config_data[CONF_LOCATION_ID].strip()

        # 检查过期域名
        deprecated_domains = ["api.qweather.com", "devapi.qweather.com", "geoapi.qweather.com"]
        if any(domain in user_host for domain in deprecated_domains):
            errors["base"] = "api_host_deprecated"

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
                # 获取系统语言进行本地化搜索
                ha_lang = self.hass.config.language
                qweather_lang = LANGUAGE_MAP.get(ha_lang, "en")
                
                res = await api.city_lookup(raw_loc, lang=qweather_lang)
                api_code = res.get("code") # 获取 API 状态码
                
                if api_code == "200" and res.get("location"):
                    self._discovered_locations = res["location"]
                    if len(self._discovered_locations) == 1:
                        return await self._async_verify_and_create(self._discovered_locations[0])
                    return await self.async_step_select_location()
                
                # --- 精细化错误分类 ---
                if api_code == "400":
                    # 细分：是参数错误还是找不到位置
                    error_title = res.get("error_detail", "")
                    if "Location" in error_title:
                        errors["base"] = "location_not_found"
                    else:
                        errors["base"] = "invalid_parameter"
                elif api_code == "401":
                    errors["base"] = "invalid_auth"
                elif api_code == "403":
                    # 细分：是没钱了还是 Host 填错了
                    error_title = res.get("error_detail", "")
                    if "Host" in error_title:
                        errors["base"] = "invalid_host"
                    elif "Credit" in error_title or "Overdue" in error_title:
                        errors["base"] = "no_credit"
                    else:
                        errors["base"] = "forbidden"
                elif api_code == "404":
                    errors["base"] = "not_found"
                elif api_code == "429":
                    errors["base"] = "too_many_requests"
                elif api_code == "500":
                    errors["base"] = "server_error"
                else:
                    errors["base"] = "cannot_connect"
                    
            except Exception as err:
                LOGGER.error("无法连接至 API Host %s: %s", user_host, err)
                errors["base"] = "cannot_connect"

        # 确定出错时应该回退到哪个步骤
        if self.source == config_entries.SOURCE_RECONFIGURE:
            step_id = "reconfigure"
        elif "reuse_from" in self._temp_data:
            step_id = "reuse_location"
        else:
            step_id = "setup"

        # 如果是 JWT 模式且还在配置阶段，回退到 jwt_setup
        if config_data.get(CONF_USE_TOKEN) and step_id != "reuse_location":
            # 注意：如果 reconfigure 过程中 JWT 校验失败，通常也应该回退到 jwt_setup 重新输入 ID
            step_id = "jwt_setup"

        return self.async_show_form(
            step_id=step_id, 
            data_schema=self._get_schema(config_data), 
            errors=errors
        )

    async def async_step_select_location(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """让用户从多个搜索结果中确认城市."""
        if user_input is not None:
            location = next(
                loc for loc in self._discovered_locations 
                if loc["id"] == user_input["location_index"]
            )
            return await self._async_verify_and_create(location)

        # 构造易读的选择列表
        options = [
            {
                "value": loc["id"],
                "label": f"{loc['name']} ({loc['adm2']}, {loc['adm1']}, {loc['country']})"
            }
            for loc in self._discovered_locations
        ]

        return self.async_show_form(
            step_id="select_location",
            data_schema=vol.Schema({
                vol.Required("location_index"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.LIST
                    )
                )
            })
        )

    async def _async_verify_and_create(self, location_info: dict[str, Any]) -> FlowResult:
        """实现地理数据标准化，锁定物理 ID 并创建条目."""
        
        # 提取标准化高精度坐标 (Lon,Lat)
        std_lon = round(float(location_info["lon"]), 2)
        std_lat = round(float(location_info["lat"]), 2)
        normalized_coords = f"{std_lon},{std_lat}"
        
        # 新临时数据
        self._temp_data[CONF_LOCATION_ID] = normalized_coords
        city_title = location_info["name"]

        # 锁定物理唯一 ID
        unique_id = f"qw_{normalized_coords.replace(',', '_')}"
        await self.async_set_unique_id(unique_id)
        
        if self.source == config_entries.SOURCE_RECONFIGURE:
            return self.async_update_reload_and_abort(self._get_reconfigure_entry(), data=self._temp_data)
        
        self._abort_if_unique_id_configured()

        # 创建集成条目
        return self.async_create_entry(
            title=city_title, 
            data=self._temp_data,
            options={
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_DAILYSTEPS: "7",
                CONF_HOURLYSTEPS: "24",
                CONF_GIRD: False,
                CONF_CUSTOM_UI: False,
            }
        )

    def _get_schema(self, data: dict) -> vol.Schema:
        """获取带有当前数据的 Schema 用于错误回显."""
        # 复用模式下的回显
        if "reuse_from" in self._temp_data:
            return vol.Schema({
                vol.Required(CONF_LOCATION_ID, default=data.get(CONF_LOCATION_ID)): selector.TextSelector()
            })
        
        # JWT 模式下的回显
        if data.get(CONF_USE_TOKEN):
            return vol.Schema({
                vol.Required(CONF_PROJECT_ID, default=data.get(CONF_PROJECT_ID)): selector.TextSelector(),
                vol.Required(CONF_KEY_ID, default=data.get(CONF_KEY_ID)): selector.TextSelector(),
            })

        # 普通 setup 模式下的全量回显
        return vol.Schema({
            vol.Required(CONF_HOST, default=data.get(CONF_HOST)): selector.TextSelector(),
            vol.Required(CONF_LOCATION_ID, default=data.get(CONF_LOCATION_ID)): selector.TextSelector(),
            vol.Required(CONF_USE_TOKEN, default=data.get(CONF_USE_TOKEN)): selector.BooleanSelector(),
            vol.Optional(CONF_API_KEY, default=data.get(CONF_API_KEY)): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        })

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """重新配置逻辑：支持切换 Key 或 JWT."""
        entry = self._get_reconfigure_entry()
        
        if user_input is not None:
            # 合并旧数据与新输入
            self._temp_data = {**entry.data, **user_input}
            
            # 如果勾选了使用 Token，跳转到 JWT 配置页
            if user_input.get(CONF_USE_TOKEN):
                return await self.async_step_jwt_setup()
            
            # 否则直接走搜索校验逻辑
            return await self._async_search_location(self._temp_data)

        # 初始显示重新配置表单
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST, "")): selector.TextSelector(),
                vol.Required(CONF_LOCATION_ID, default=entry.data.get(CONF_LOCATION_ID, "")): selector.TextSelector(),
                vol.Required(CONF_USE_TOKEN, default=entry.data.get(CONF_USE_TOKEN, False)): selector.BooleanSelector(),
                vol.Optional(CONF_API_KEY, default=entry.data.get(CONF_API_KEY, "")): selector.TextSelector(
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
                vol.Required(
                    CONF_UPDATE_INTERVAL, 
                    default=options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=1440, step=1, mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_DAILYSTEPS, 
                    default=str(options.get(CONF_DAILYSTEPS, 7))
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["3", "7", "10", "15", "30"],
                        mode=selector.SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Required(
                    CONF_HOURLYSTEPS, 
                    default=str(options.get(CONF_HOURLYSTEPS, 24))
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["24", "72", "168"],
                        mode=selector.SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Required(CONF_GIRD, default=options.get(CONF_GIRD, False)): selector.BooleanSelector(),
                vol.Required(CONF_CUSTOM_UI, default=options.get(CONF_CUSTOM_UI, False)): selector.BooleanSelector(),
            }),
        )