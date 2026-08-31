"""QWeather (和风天气) 配置流实现."""
from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Final

import voluptuous as vol
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations

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
    CONF_ISS,
    CONF_JWT_RECONFIGURE_CHOICE,
    CONF_CUSTOM_UI,
    CONF_CUSTOM_MORE_INFO,
    DEFAULT_UPDATE_INTERVAL,
    LANGUAGE_MAP,
    LOGGER,
)

# 和风天气控制台地址（配置流多处引用，统一常量）
QWEATHER_CONSOLE_URL: Final = "https://console.qweather.com"

class QWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """处理和风天气的配置流."""

    VERSION = 1

    def __init__(self) -> None:
        """初始化临时变量."""
        self._temp_data: dict[str, Any] = {}
        self._discovered_locations: list[dict[str, Any]] = []
        self._generated_private_key: str | None = None
        self._generated_public_key: str | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None

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

    def _derive_public_key_sync(self, private_pem: str) -> str:
        """从存储的私钥反推公钥（用于「保留原配置」模式展示核对，不重新生成）。"""
        private_key = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return public_bytes.decode("utf-8")

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
        
            self._temp_data["reuse_from"] = selection
            return await self.async_step_reuse_location()

        # 构造“复用或新建”的选择列表
        account_options = [{"value": "new_account", "label": "new_account"}]
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
                vol.Required(CONF_USE_TOKEN, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }),
            description_placeholders={
                "qweather_console": QWEATHER_CONSOLE_URL
            }
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
        """JWT 身份验证步骤（默认鉴权方式；API KEY 将自 2027-01-01 起受每日限额且 SDK 5+ 不再支持，故默认 JWT）."""
        # 重配「保留原配置」进入时已带旧 private_key → 复用既有密钥，不静默重生
        existing_private = self._temp_data.get(CONF_PRIVATE_KEY)
        is_reuse = bool(existing_private)

        if user_input is not None:
            if not is_reuse:
                # 首次 JWT /「重新生成 JWT」分支：复用展示阶段已生成的密钥对，
                if not self._generated_private_key:
                    self._generated_private_key, self._generated_public_key = await self.hass.async_add_executor_job(
                        self._generate_key_pair_sync
                    )
            else:
                # 保留原密钥：复用既有私钥，公钥从私钥派生用于展示核对
                self._generated_private_key = existing_private
                self._generated_public_key = await self.hass.async_add_executor_job(
                    self._derive_public_key_sync, existing_private
                )

            self._temp_data.update(user_input)
            self._temp_data[CONF_PRIVATE_KEY] = self._generated_private_key
            return await self._async_search_location(self._temp_data)

        # 展示表单：首次 JWT 预先生成密钥对以展示公钥
        if not is_reuse and not self._generated_private_key:
            self._generated_private_key, self._generated_public_key = await self.hass.async_add_executor_job(
                self._generate_key_pair_sync
            )
        # 保留模式：从存储私钥派生公钥供核对（私钥已在 temp_data，不重新生成）
        if is_reuse and not self._generated_public_key:
            self._generated_public_key = await self.hass.async_add_executor_job(
                self._derive_public_key_sync, existing_private
            )

        schema_fields: dict = {
            vol.Optional(CONF_ISS, default=self._temp_data.get(CONF_ISS, "")): selector.TextSelector(),
            vol.Required(CONF_PROJECT_ID, default=self._temp_data.get(CONF_PROJECT_ID, "")): selector.TextSelector(),
            vol.Required(CONF_KEY_ID, default=self._temp_data.get(CONF_KEY_ID, "")): selector.TextSelector(),
        }

        # 取翻译：首次/重新生成模式展示「步骤 + 公钥代码块」，保留模式展示「原公钥 + 复用提示」。
        # 注意：first_block/reuse_block/sha256_label 位于 config.step.jwt_setup.description_placeholders
        # （HA 配置流翻译 schema 禁止在 step 顶层出现自定义键，否则 hassfest 报 not a valid option）。
        translations = await async_get_translations(self.hass, self.hass.config.language, "config", [DOMAIN])
        jwt_dp = translations.get(f"component.{DOMAIN}.config.step.jwt_setup.description_placeholders", {})
        first_block = jwt_dp.get("first_block", "")
        reuse_block = jwt_dp.get("reuse_block", "")
        if self._generated_public_key:
            pub_pem = self._generated_public_key
            # 公钥 SHA256 指纹：供用户去和风控制台比对「本地私钥 ↔ 控制台公钥」是否同一把，
            pub_sha256 = hashlib.sha256(pub_pem.strip().encode("utf-8")).hexdigest()
            sha256_label = jwt_dp.get("sha256_label", "SHA256: ")
            key_block = (
                "\r\n```text\r\n" + pub_pem + "\r\n```\r\n"
                + sha256_label + pub_sha256
            )
            # 保留模式展示原公钥 + 复用提示；首次/重新生成模式展示步骤 + 新公钥
            placeholders = {"upload_block": (reuse_block if is_reuse else first_block) + key_block}
        else:
            placeholders = {"upload_block": reuse_block}

        return self.async_show_form(
            step_id="jwt_setup",
            data_schema=vol.Schema(schema_fields),
            description_placeholders=placeholders,
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
                iss=config_data.get(CONF_ISS),
                host=user_host
            )

            try:
                # 获取系统语言进行本地化搜索
                ha_lang = self.hass.config.language
                qweather_lang = LANGUAGE_MAP.get(ha_lang, "en")
                
                res = await api.city_lookup(raw_loc, lang=qweather_lang)
                api_code = res.get("code") # 获取 API 状态码
                if api_code != "200":
                    LOGGER.error(
                        "QWeather 城市校验未通过: code=%s | detail=%s",
                        api_code, res.get("error_detail"),
                    )
                
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
        options = {
            CONF_DAILYSTEPS: "7",
            CONF_HOURLYSTEPS: "24",
            CONF_CUSTOM_UI: False,
            CONF_CUSTOM_MORE_INFO: False,
        }
        # API KEY 认证不写 update_interval：coordinator 强制 API_KEY_UPDATE_INTERVAL(100)，不可由用户更改
        if self._temp_data.get(CONF_USE_TOKEN):
            options[CONF_UPDATE_INTERVAL] = DEFAULT_UPDATE_INTERVAL
        return self.async_create_entry(
            title=city_title,
            data=self._temp_data,
            options=options,
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
            fields: dict = {
                vol.Optional(CONF_ISS, default=data.get(CONF_ISS) or ""): selector.TextSelector(),
                vol.Required(CONF_PROJECT_ID, default=data.get(CONF_PROJECT_ID)): selector.TextSelector(),
                vol.Required(CONF_KEY_ID, default=data.get(CONF_KEY_ID)): selector.TextSelector(),
            }
            return vol.Schema(fields)

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

            # 如果勾选了使用 Token，进入 JWT 重新配置分支选择
            if user_input.get(CONF_USE_TOKEN):
                # 切到 JWT：清理对侧冗余的 API KEY 凭据（JWT 模式不使用）
                self._temp_data.pop(CONF_API_KEY, None)
                return await self.async_step_reconfigure_jwt_choice()

            # 切回 API KEY：清理对侧冗余的 JWT 凭据，避免旧私钥/ID 残留落库
            for key in (CONF_ISS, CONF_PROJECT_ID, CONF_KEY_ID, CONF_PRIVATE_KEY):
                self._temp_data.pop(key, None)
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

    async def async_step_reconfigure_jwt_choice(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """重新配置 JWT 分支选择：保留原配置（复用密钥，字段预填）或 重新生成 JWT（全新密钥对，清空字段）."""
        # Key→JWT 迁移：原条目没有 JWT 私钥，无「保留原配置」可言。
        # 两个选项行为完全一致（都生成新密钥对），无需让用户二选一，直接进入 jwt_setup 生成全新密钥对。
        if user_input is None and not self._temp_data.get(CONF_PRIVATE_KEY):
            return await self.async_step_jwt_setup()

        if user_input is not None:
            if user_input.get(CONF_JWT_RECONFIGURE_CHOICE) == "regenerate":
                # 全新：清空 JWT 认证字段，jwt_setup 将以空表单 + 重新生成密钥对呈现
                for key in (CONF_ISS, CONF_PROJECT_ID, CONF_KEY_ID, CONF_PRIVATE_KEY):
                    self._temp_data.pop(key, None)
            # keep_current：保留原 iss/project_id/key_id/private_key，jwt_setup 预填并复用密钥
            return await self.async_step_jwt_setup()

        return self.async_show_form(
            step_id="reconfigure_jwt_choice",
            data_schema=vol.Schema({
                vol.Required(CONF_JWT_RECONFIGURE_CHOICE, default="keep_current"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "keep_current", "label": "keep_current"},
                            {"value": "regenerate", "label": "regenerate"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="jwt_reconfigure_choice",
                    )
                )
            }),
        )

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """认证失效后的入口步骤：载入原条目并引导重新输入凭据."""
        entry_id = self.context.get("entry_id")
        self._reauth_entry = (
            self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        )
        if self._reauth_entry is None:
            return self.async_abort(reason="reauth_failed_entry_not_found")

        # 预填原凭据，仅覆盖认证相关字段，不改变城市/位置
        self._temp_data = dict(self._reauth_entry.data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """重认证：更新 API Host / 认证方式 / API Key."""
        if user_input is not None:
            self._temp_data.update(user_input)
            if user_input.get(CONF_USE_TOKEN):
                return await self.async_step_reauth_jwt()
            return await self._async_finish_reauth()

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self._reauth_schema(),
        )

    async def async_step_reauth_jwt(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """重认证：JWT 凭据 (生成密钥对 + 展示公钥)."""
        if user_input is not None:
            self._temp_data.update(user_input)
            return await self._async_finish_reauth()

        # 确保密钥对存在：API KEY 切 JWT 时无既有私钥，须本地生成；
        # 既有 JWT 条目重认证则复用私钥并派生公钥供核对。
        existing_private = self._temp_data.get(CONF_PRIVATE_KEY)
        if not existing_private:
            self._generated_private_key, self._generated_public_key = await self.hass.async_add_executor_job(
                self._generate_key_pair_sync
            )
            self._temp_data[CONF_PRIVATE_KEY] = self._generated_private_key
            is_reuse = False
        else:
            self._generated_private_key = existing_private
            self._generated_public_key = await self.hass.async_add_executor_job(
                self._derive_public_key_sync, existing_private
            )
            is_reuse = True

        translations = await async_get_translations(self.hass, self.hass.config.language, "config", [DOMAIN])
        jwt_dp = translations.get(f"component.{DOMAIN}.config.step.jwt_setup.description_placeholders", {})
        first_block = jwt_dp.get("first_block", "")
        reuse_block = jwt_dp.get("reuse_block", "")
        if self._generated_public_key:
            pub_sha256 = hashlib.sha256(self._generated_public_key.strip().encode("utf-8")).hexdigest()
            sha256_label = jwt_dp.get("sha256_label", "SHA256: ")
            key_block = (
                "\r\n```text\r\n" + self._generated_public_key + "\r\n```\r\n"
                + sha256_label + pub_sha256
            )
            placeholders = {"upload_block": (reuse_block if is_reuse else first_block) + key_block}
        else:
            placeholders = {"upload_block": reuse_block}

        return self.async_show_form(
            step_id="reauth_jwt",
            data_schema=self._reauth_schema(),
            description_placeholders=placeholders,
        )

    def _reauth_schema(self) -> vol.Schema:
        """重认证表单：按认证方式动态构造 (不包含地理位置字段)."""
        if self._temp_data.get(CONF_USE_TOKEN):
            return vol.Schema({
                vol.Optional(CONF_ISS, default=self._temp_data.get(CONF_ISS, "")): selector.TextSelector(),
                vol.Required(CONF_PROJECT_ID, default=self._temp_data.get(CONF_PROJECT_ID, "")): selector.TextSelector(),
                vol.Required(CONF_KEY_ID, default=self._temp_data.get(CONF_KEY_ID, "")): selector.TextSelector(),
            })
        return vol.Schema({
            vol.Required(CONF_HOST, default=self._temp_data.get(CONF_HOST, "")): selector.TextSelector(),
            vol.Required(CONF_USE_TOKEN, default=self._temp_data.get(CONF_USE_TOKEN, False)): selector.BooleanSelector(),
            vol.Optional(CONF_API_KEY, default=self._temp_data.get(CONF_API_KEY, "")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        })

    @staticmethod
    def _reauth_error_key(api_code: str | None, error_detail: str = "") -> str:
        """将 API 错误码映射为翻译错误 key (与设置流程分类保持一致)."""
        if api_code == "401":
            return "invalid_auth"
        if api_code == "403":
            if "Host" in error_detail:
                return "invalid_host"
            if "Credit" in error_detail or "Overdue" in error_detail:
                return "no_credit"
            return "forbidden"
        if api_code == "400":
            return "invalid_parameter"
        if api_code == "404":
            return "not_found"
        if api_code == "429":
            return "too_many_requests"
        if api_code == "500":
            return "server_error"
        return "cannot_connect"

    async def _async_finish_reauth(self) -> FlowResult:
        """校验新凭据 (使用原位置做一次城市搜索) 并更新配置条目."""
        assert self._reauth_entry is not None
        entry = self._reauth_entry
        errors: dict[str, str] = {}

        api = QWeatherAPI(
            session=async_get_clientsession(self.hass),
            api_key=self._temp_data.get(CONF_API_KEY),
            use_token=self._temp_data.get(CONF_USE_TOKEN),
            project_id=self._temp_data.get(CONF_PROJECT_ID),
            key_id=self._temp_data.get(CONF_KEY_ID),
            private_key=self._temp_data.get(CONF_PRIVATE_KEY),
            iss=self._temp_data.get(CONF_ISS),
            host=self._temp_data.get(CONF_HOST),
        )

        try:
            ha_lang = self.hass.config.language
            qweather_lang = LANGUAGE_MAP.get(ha_lang, "en")
            res = await api.city_lookup(entry.data.get(CONF_LOCATION_ID), lang=qweather_lang)
            api_code = res.get("code")
            if api_code == "200":
                self.hass.config_entries.async_update_entry(entry, data=self._temp_data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            errors["base"] = self._reauth_error_key(api_code, res.get("error_detail", ""))
        except Exception as err:
            LOGGER.error("QWeather 重认证凭据校验失败: %s", err)
            errors["base"] = "cannot_connect"

        step_id = "reauth_jwt" if self._temp_data.get(CONF_USE_TOKEN) else "reauth_confirm"
        return self.async_show_form(
            step_id=step_id,
            data_schema=self._reauth_schema(),
            errors=errors,
        )

class QWeatherOptionsFlow(config_entries.OptionsFlow):
    """处理已安装集成的 UI 选项配置."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """选项配置主界面."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        use_token = self.config_entry.data.get(CONF_USE_TOKEN)

        fields: dict = {}
        # API KEY 认证下轮询间隔强制为 100 分钟（coordinator 强制），不在条目配置中暴露，用户不可更改
        if use_token:
            fields[vol.Required(
                CONF_UPDATE_INTERVAL,
                default=options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            )] = selector.NumberSelector(
                selector.NumberSelectorConfig(min=5, max=1440, step=1, mode=selector.NumberSelectorMode.BOX)
            )
        fields[vol.Required(
            CONF_DAILYSTEPS,
            default=str(options.get(CONF_DAILYSTEPS, 7))
        )] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                # V1 每日预报仅支持 1-10 天
                options=["3", "7", "10"],
                mode=selector.SelectSelectorMode.DROPDOWN
            )
        )
        fields[vol.Required(
            CONF_HOURLYSTEPS,
            default=str(options.get(CONF_HOURLYSTEPS, 24))
        )] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=["24", "72", "168"],
                mode=selector.SelectSelectorMode.DROPDOWN
            )
        )
        fields[vol.Required(CONF_CUSTOM_UI, default=options.get(CONF_CUSTOM_UI, False))] = selector.BooleanSelector()
        fields[vol.Required(CONF_CUSTOM_MORE_INFO, default=options.get(CONF_CUSTOM_MORE_INFO, False))] = selector.BooleanSelector()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(fields),
        )