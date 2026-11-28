"""QWeather (和风天气) 配置流实现（账号条目 + location 子条目）."""
from __future__ import annotations

import hashlib
from typing import Any, Final, Mapping

import voluptuous as vol
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from homeassistant import config_entries
from homeassistant.core import callback, HomeAssistant
from homeassistant.const import CONF_HOST, CONF_API_KEY
from homeassistant.exceptions import ConfigEntryAuthFailed
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
    CONF_ISS,
    CONF_JWT_RECONFIGURE_CHOICE,
    CONF_CUSTOM_UI,
    CONF_CUSTOM_MORE_INFO,
    SUBENTRY_TYPE_LOCATION,
    get_location_subentries,
    DEFAULT_UPDATE_INTERVAL,
    LANGUAGE_MAP,
    location_options_data,
    LOGGER,
)

# 和风天气控制台地址（配置流多处引用，统一常量）
QWEATHER_CONSOLE_URL: Final = "https://console.qweather.com"
# 已废弃的旧域名（v1 API 迁移后不可用）
_DEPRECATED_DOMAINS: Final = ("api.qweather.com", "devapi.qweather.com", "geoapi.qweather.com")
# 鉴权类错误：JWT 凭据可能填错，回退 jwt_setup 让用户修正 project_id/key_id
_AUTH_ERRORS: Final = ("invalid_auth", "forbidden", "no_credit")


def _default_location(hass: HomeAssistant) -> str:
    """以 HA 配置的经纬度作为位置输入默认值."""
    return f"{round(hass.config.longitude, 2)},{round(hass.config.latitude, 2)}"


def _location_unique_id(coords: str) -> str:
    """位置子条目 unique_id（父条目内唯一）."""
    return f"qw_{coords.replace(',', '_')}"


def _account_unique_id(data: dict[str, Any]) -> str:
    """账号条目 unique_id：专属 API Host 每账号唯一（同 host 禁止重复添加）."""
    return data[CONF_HOST].strip()


def _location_options_schema_fields(
    use_token: bool, current: Mapping[str, Any]
) -> dict:
    """位置 options 表单字段（子条目 user / reconfigure 共用）。"""
    fields: dict = {}
    # API KEY 认证下轮询间隔强制为 100 分钟（coordinator 强制），不暴露控件
    if use_token:
        fields[vol.Required(
            CONF_UPDATE_INTERVAL,
            default=current.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=5, max=1440, step=1, mode=selector.NumberSelectorMode.BOX)
        )
    fields[vol.Required(
        CONF_DAILYSTEPS,
        default=str(current.get(CONF_DAILYSTEPS, 7)),
    )] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            # V1 每日预报仅支持 1-10 天
            options=["3", "7", "10"],
            mode=selector.SelectSelectorMode.DROPDOWN
        )
    )
    fields[vol.Required(
        CONF_HOURLYSTEPS,
        default=str(current.get(CONF_HOURLYSTEPS, 24)),
    )] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=["24", "72", "168"],
            mode=selector.SelectSelectorMode.DROPDOWN
        )
    )
    fields[vol.Required(CONF_CUSTOM_UI, default=current.get(CONF_CUSTOM_UI, False))] = selector.BooleanSelector()
    fields[vol.Required(CONF_CUSTOM_MORE_INFO, default=current.get(CONF_CUSTOM_MORE_INFO, False))] = selector.BooleanSelector()
    return fields


async def _async_search_city(
    hass: HomeAssistant, api: QWeatherAPI, query: str
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """城市搜索 + 错误码分类（账号流与位置子条目流共用）。成功返回 (候选, {})。"""
    errors: dict[str, str] = {}
    try:
        ha_lang = hass.config.language
        qweather_lang = LANGUAGE_MAP.get(ha_lang, "en")
        res = await api.city_lookup(query, lang=qweather_lang)
        api_code = res.get("code")
        if api_code != "200":
            LOGGER.error(
                "QWeather 城市校验未通过: code=%s | detail=%s",
                api_code, res.get("error_detail"),
            )
        if api_code == "200" and res.get("location"):
            return res["location"], {}
        if api_code == "400":
            error_title = res.get("error_detail", "")
            errors["base"] = "location_not_found" if "Location" in error_title else "invalid_parameter"
        elif api_code == "401":
            errors["base"] = "invalid_auth"
        elif api_code == "403":
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
    except ConfigEntryAuthFailed:
        # api 层本地判定认证失败（私钥缺失/损坏无法生成 JWT）→ 归为鉴权错误
        errors["base"] = "invalid_auth"
    except Exception as err:
        LOGGER.error("无法连接至 API Host: %s", err)
        errors["base"] = "cannot_connect"
    return [], errors


class QWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """处理和风天气的配置流（条目 = 账号，首个位置随条目创建）."""

    VERSION = 2
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """初始化临时变量."""
        self._temp_data: dict[str, Any] = {}
        self._discovered_locations: list[dict[str, Any]] = []
        self._generated_private_key: str | None = None
        self._generated_public_key: str | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None
        # jwt_setup 表单回退时暂存的错误（经 async_step_jwt_setup 完整渲染时带入）
        self._jwt_form_errors: dict[str, str] | None = None

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: config_entries.ConfigEntry
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        """声明位置子条目流."""
        return {"location": LocationSubentryFlow}

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

    def _key_block_placeholders(self) -> dict[str, str]:
        """公钥 + SHA256 指纹代码块（经 description 的 {key_block} 占位符注入）。"""
        if not self._generated_public_key:
            return {}
        pub_pem = self._generated_public_key
        pub_sha256 = hashlib.sha256(pub_pem.strip().encode("utf-8")).hexdigest()
        return {
            "key_block": (
                "\r\n```text\r\n" + pub_pem + "\r\n```\r\n" + "SHA256: " + pub_sha256
            )
        }

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """入口步骤：新建账号（首次位置一并创建；加城市走条目页的子条目入口）."""
        return await self.async_step_setup(user_input)

    async def async_step_setup(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """标准设置页面."""
        if user_input is not None:
            self._temp_data.update(user_input)
            if user_input.get(CONF_USE_TOKEN):
                return await self.async_step_jwt_setup()
            return await self._async_search_location(self._temp_data)

        return self.async_show_form(
            step_id="setup",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): selector.TextSelector(),
                vol.Required(CONF_LOCATION_ID, default=_default_location(self.hass)): selector.TextSelector(),
                vol.Required(CONF_USE_TOKEN, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }),
            description_placeholders={
                "qweather_console": QWEATHER_CONSOLE_URL
            }
        )

    async def async_step_jwt_setup(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """JWT 身份验证步骤（默认鉴权方式；API KEY 将自 2027-01-01 起受每日限额且 SDK 5+ 不再支持，故默认 JWT）."""
        # 重配「保留原配置」进入时已带旧 private_key → 复用既有密钥，不静默重生
        existing_private = self._temp_data.get(CONF_PRIVATE_KEY)
        is_reuse = bool(existing_private)

        if user_input is not None:
            self._jwt_form_errors = None
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
            if self.source == config_entries.SOURCE_RECONFIGURE:
                return await self._async_finish_reconfigure()
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
        # 公钥说明内联进 translations：step 级 schema 不接受自定义键（hassfest 拒绝）
        return self.async_show_form(
            step_id="jwt_setup",
            data_schema=vol.Schema(schema_fields),
            description_placeholders=self._key_block_placeholders(),
            errors=self._jwt_form_errors,
        )

    async def _async_validate_credentials(
        self, config_data: dict[str, Any], query: str
    ) -> dict[str, str] | None:
        """验证账号凭据（以给定位置做搜索探针）。成功返回 None 并填充候选列表。"""
        user_host = config_data[CONF_HOST].strip()
        if any(domain in user_host for domain in _DEPRECATED_DOMAINS):
            return {"base": "api_host_deprecated"}
        api = QWeatherAPI(
            session=async_get_clientsession(self.hass),
            api_key=config_data.get(CONF_API_KEY),
            use_token=config_data.get(CONF_USE_TOKEN),
            project_id=config_data.get(CONF_PROJECT_ID),
            key_id=config_data.get(CONF_KEY_ID),
            private_key=config_data.get(CONF_PRIVATE_KEY),
            iss=config_data.get(CONF_ISS),
            host=user_host,
        )
        locations, errors = await _async_search_city(self.hass, api, query.strip())
        if errors:
            return errors
        self._discovered_locations = locations
        return None

    async def _async_search_location(self, config_data: dict[str, Any]) -> FlowResult:
        """新建条目路径：用表单位置做探针验证凭据，通过后创建条目."""
        errors = await self._async_validate_credentials(
            config_data, config_data[CONF_LOCATION_ID]
        )
        if errors is None:
            if len(self._discovered_locations) == 1:
                return await self._async_verify_and_create(self._discovered_locations[0])
            return await self.async_step_select_location()

        # 回退策略：仅鉴权类错误（JWT 凭据可能填错）才回退 jwt_setup 修正 project_id/key_id
        if config_data.get(CONF_USE_TOKEN) and errors.get("base") in _AUTH_ERRORS:
            self._jwt_form_errors = errors
            return await self.async_step_jwt_setup()
        return self.async_show_form(
            step_id="setup",
            data_schema=self._setup_schema(config_data),
            errors=errors,
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
        """实现地理数据标准化并创建账号条目（首个位置随条目落库）."""

        # 提取标准化高精度坐标 (Lon,Lat)
        std_lon = round(float(location_info["lon"]), 2)
        std_lat = round(float(location_info["lat"]), 2)
        normalized_coords = f"{std_lon},{std_lat}"
        self._temp_data[CONF_LOCATION_ID] = normalized_coords
        city_title = location_info["name"]

        # 锁定账号唯一 ID：host 即账号身份，同 host 禁止重复添加
        await self.async_set_unique_id(_account_unique_id(self._temp_data))
        self._abort_if_unique_id_configured()

        # 创建集成条目：条目 = 账号（title=host），凭据在 data，options 全部下沉子条目（R4）
        use_token = bool(self._temp_data.get(CONF_USE_TOKEN))
        first_location_data: dict[str, Any] = {
            CONF_LOCATION_ID: normalized_coords,
            **location_options_data(
                use_token, {k: v for k, v in self._temp_data.items() if k != CONF_LOCATION_ID}
            ),
        }
        return self.async_create_entry(
            title=self._temp_data[CONF_HOST].strip(),
            data={k: v for k, v in self._temp_data.items() if k != CONF_LOCATION_ID},
            subentries=[{
                "subentry_type": SUBENTRY_TYPE_LOCATION,
                "title": city_title,
                "data": first_location_data,
                "unique_id": _location_unique_id(normalized_coords),
            }],
        )

    def _setup_schema(self, data: dict) -> vol.Schema:
        """新建条目全量回显（含 host：host/连接类错误只有这里能改 host）."""
        return vol.Schema({
            vol.Required(CONF_HOST, default=data.get(CONF_HOST)): selector.TextSelector(),
            vol.Required(CONF_LOCATION_ID, default=data.get(CONF_LOCATION_ID)): selector.TextSelector(),
            vol.Required(CONF_USE_TOKEN, default=data.get(CONF_USE_TOKEN)): selector.BooleanSelector(),
            vol.Optional(CONF_API_KEY, default=data.get(CONF_API_KEY)): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        })

    def _account_reconfigure_schema(self, data: dict) -> vol.Schema:
        """账号重配表单（无位置字段；凭据变更对全部位置生效）."""
        return vol.Schema({
            vol.Required(CONF_HOST, default=data.get(CONF_HOST, "")): selector.TextSelector(),
            vol.Required(CONF_USE_TOKEN, default=data.get(CONF_USE_TOKEN, False)): selector.BooleanSelector(),
            vol.Optional(CONF_API_KEY, default=data.get(CONF_API_KEY, "")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        })

    def _first_probe_location(self, entry: config_entries.ConfigEntry) -> str | None:
        """取首个位置坐标作凭据验证探针（账号流无位置字段后唯一的探测手段）。"""
        subentries = get_location_subentries(entry)
        return subentries[0].data[CONF_LOCATION_ID] if subentries else None

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """重新配置账号：支持切换 Key 或 JWT."""
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
            return await self._async_finish_reconfigure()

        # 初始显示重新配置表单
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._account_reconfigure_schema(entry.data),
        )

    async def _async_finish_reconfigure(self) -> FlowResult:
        """校验账号凭据（以首个位置做探针）并更新条目（reload 由 update listener 完成）."""
        entry = self._get_reconfigure_entry()
        probe = self._first_probe_location(entry)
        if probe is None:
            errors: dict[str, str] = {"base": "location_not_found"}
        else:
            errors = await self._async_validate_credentials(self._temp_data, probe) or {}

        if not errors:
            return self.async_update_and_abort(
                entry,
                data={k: v for k, v in self._temp_data.items() if k != CONF_LOCATION_ID},
            )

        if self._temp_data.get(CONF_USE_TOKEN) and errors.get("base") in _AUTH_ERRORS:
            self._jwt_form_errors = errors
            return await self.async_step_jwt_setup()
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._account_reconfigure_schema(self._temp_data),
            errors=errors,
        )

    async def async_step_reconfigure_jwt_choice(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """重新配置 JWT 分支选择：保留原配置（复用密钥，字段预填）或 重新生成 JWT（全新密钥对，清空字段）."""
        # Key→JWT 迁移无既有私钥，两选项行为一致，直接进入 jwt_setup
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

        # 预填原凭据，仅覆盖认证相关字段，不改变位置
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

        # 确保密钥对存在：Key→JWT 需本地生成，重认证复用既有私钥
        existing_private = self._temp_data.get(CONF_PRIVATE_KEY)
        if not existing_private:
            self._generated_private_key, self._generated_public_key = await self.hass.async_add_executor_job(
                self._generate_key_pair_sync
            )
            self._temp_data[CONF_PRIVATE_KEY] = self._generated_private_key
        else:
            self._generated_private_key = existing_private
            self._generated_public_key = await self.hass.async_add_executor_job(
                self._derive_public_key_sync, existing_private
            )

        # 公钥代码块说明文本已内联进 translations 的 reauth_jwt.description。
        return self.async_show_form(
            step_id="reauth_jwt",
            data_schema=self._reauth_schema(),
            description_placeholders=self._key_block_placeholders(),
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
        """校验新凭据 (使用首个位置做城市搜索) 并更新配置条目."""
        assert self._reauth_entry is not None
        entry = self._reauth_entry
        probe = self._first_probe_location(entry)
        if probe is None:
            errors: dict[str, str] = {"base": "location_not_found"}
        else:
            errors = await self._async_validate_credentials(self._temp_data, probe) or {}

        if not errors:
            self.hass.config_entries.async_update_entry(
                entry,
                data={k: v for k, v in self._temp_data.items() if k != CONF_LOCATION_ID},
            )
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        step_id = "reauth_jwt" if self._temp_data.get(CONF_USE_TOKEN) else "reauth_confirm"
        return self.async_show_form(
            step_id=step_id,
            data_schema=self._reauth_schema(),
            errors=errors,
        )


class LocationSubentryFlow(config_entries.ConfigSubentryFlow):
    """位置子条目流：添加=纯位置搜索，reconfigure 仅改 options."""

    def __init__(self) -> None:
        """初始化临时变量."""
        self._discovered_locations: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """添加位置（纯位置搜索）."""
        entry = self._get_entry()
        if entry.state is not config_entries.ConfigEntryState.LOADED:
            return self.async_abort(reason="config_entry_not_loaded")
        if user_input is not None:
            return await self._async_search(user_input[CONF_LOCATION_ID])
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_LOCATION_ID, default=_default_location(self.hass)): selector.TextSelector(),
            }),
        )

    async def _async_search(self, query: str) -> config_entries.SubentryFlowResult:
        entry = self._get_entry()
        if entry.state is not config_entries.ConfigEntryState.LOADED:
            return self.async_abort(reason="config_entry_not_loaded")
        locations, errors = await _async_search_city(
            self.hass, entry.runtime_data.api, query.strip()
        )
        if errors:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_LOCATION_ID, default=query): selector.TextSelector(),
                }),
                errors=errors,
            )
        self._discovered_locations = locations
        if len(locations) == 1:
            return self._async_create_location(locations[0])
        return await self.async_step_select_location()

    async def async_step_select_location(self, user_input: dict[str, Any] | None = None) -> config_entries.SubentryFlowResult:
        """从多个搜索结果中确认城市."""
        if user_input is not None:
            location = next(
                loc for loc in self._discovered_locations
                if loc["id"] == user_input["location_index"]
            )
            return self._async_create_location(location)
        options_list = [
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
                        options=options_list,
                        mode=selector.SelectSelectorMode.LIST
                    )
                )
            })
        )

    def _async_create_location(self, location_info: dict[str, Any]) -> config_entries.SubentryFlowResult:
        """标准化坐标、查重并创建位置子条目（options 落默认值，编辑走 reconfigure）."""
        std_lon = round(float(location_info["lon"]), 2)
        std_lat = round(float(location_info["lat"]), 2)
        coords = f"{std_lon},{std_lat}"
        uid = _location_unique_id(coords)
        entry = self._get_entry()
        if uid in {s.unique_id for s in get_location_subentries(entry)}:
            return self.async_abort(reason="duplicate_location")
        return self.async_create_entry(
            title=location_info["name"],
            data={
                CONF_LOCATION_ID: coords,
                **location_options_data(bool(entry.data.get(CONF_USE_TOKEN)), {}),
            },
            unique_id=uid,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> config_entries.SubentryFlowResult:
        """修改位置 options（位置本身不可改；改位置请删除后重新添加）."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        if entry.state is not config_entries.ConfigEntryState.LOADED:
            return self.async_abort(reason="config_entry_not_loaded")
        if user_input is not None:
            # 仅更新 options 字段，位置 data 原样保留（subentry_id/实体零变化）
            return self.async_update_and_abort(
                entry,
                subentry,
                data={
                    **subentry.data,
                    **location_options_data(bool(entry.data.get(CONF_USE_TOKEN)), user_input),
                },
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                _location_options_schema_fields(
                    bool(entry.data.get(CONF_USE_TOKEN)), subentry.data
                )
            ),
        )
