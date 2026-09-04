"""QWeather (和风天气) API 客户端."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import jwt
from aiohttp import ClientSession
from cryptography.hazmat.primitives import serialization
from homeassistant.exceptions import ConfigEntryAuthFailed
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from .const import DOMAIN, LOGGER

class QWeatherAPI:
    """和风天气 API 高级封装客户端."""

    def __init__(
        self, 
        session: ClientSession, 
        api_key: str | None = None,
        use_token: bool = False,
        project_id: str | None = None,
        key_id: str | None = None,
        private_key: str | None = None,
        iss: str | None = None,
        host: str | None = None
    ) -> None:
        self.session = session
        self.api_key = api_key
        self.use_token = use_token
        self.project_id = project_id
        self.key_id = key_id
        self.private_key = private_key
        self.iss = iss
        self._private_key_obj = None  # 缓存解析后的私钥对象，避免每次请求在事件循环上重解析 PEM
        self.host = self._normalize_host(host)

    @staticmethod
    def _normalize_host(host: str | None) -> str:
        """清理 Host：去空白、去协议前缀、去尾斜杠，避免拼出 https://https://..."""
        if not host:
            return ""
        host = host.strip().rstrip("/")
        if "://" in host:
            host = host.split("://", 1)[1]
        return host

    def _generate_jwt(self) -> str | None:
        """生成符合 EdDSA 算法的 JWT 签名."""
        try:
            if not self.private_key:
                return None

            if self._private_key_obj is None:
                self._private_key_obj = serialization.load_pem_private_key(
                    self.private_key.encode('utf-8'), password=None
                )
            private_key_obj = self._private_key_obj

            now_ts = int(time.time())
            payload = {
                'sub': self.project_id,
                'iat': now_ts - 30,   # 解决服务器时钟不同步
                'exp': now_ts + 900    # 有效期 15 分钟
            }

            if self.iss and self.iss.strip():
                payload['iss'] = self.iss.strip()
            headers = {'kid': self.key_id}
            
            return jwt.encode(
                payload, 
                private_key_obj, 
                algorithm='EdDSA', 
                headers=headers
            )
        except Exception as err:
            LOGGER.error("QWeather JWT 签名生成失败: %s", err)
            return None

    @retry(
        wait=wait_exponential(multiplier=2, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_not_exception_type(ConfigEntryAuthFailed),
    )
    async def request(self, version_path: str, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """统一底层异步请求方法 (3 次重试后异常正常抛出，由调用方处理)."""

        params = {k: v for k, v in params.items() if v is not None}
        # 路径适配：V1 版本特殊处理，其他版本直接使用 version_path
        real_version = "geo/v2" if version_path == "v2" else version_path
        # 如果 endpoint 包含占位符 {lat}/{lon}，则进行替换
        if "{lat}" in endpoint and "lat" in params and "lon" in params:
            url_endpoint = endpoint.format(lat=params.pop("lat"), lon=params.pop("lon"))
        else:
            url_endpoint = endpoint

        url = f"https://{self.host}/{real_version}/{url_endpoint}"

        headers = {
            "User-Agent": "HomeAssistant-QWeatherPro/2.0",
            "Accept-Encoding": "gzip"
        }

        if self.use_token:
            token = self._generate_jwt()
            if not token:

                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN,
                    translation_key="jwt_private_key_invalid",
                )
            headers["Authorization"] = f"Bearer {token}"
        elif self.api_key:
            headers["X-QW-Api-Key"] = self.api_key

        try:
            async with asyncio.timeout(15):
                resp = await self.session.get(url, params=params, headers=headers)
                # 即使是错误，也要尝试解析 JSON，因为 V2 规范在 Body 里包含详细原因
                try:
                    data = await resp.json()
                except Exception:
                    data = {}

                # 如果不是 200，则在返回字典中强制注入 http_status
                if resp.status != 200:
                    # 打印和风返回的真实错误体（code/title/detail），用于定位 401 等鉴权失败的根因
                    err_obj = data.get("error", {}) if isinstance(data, dict) else {}
                    qw_code = data.get("code") if isinstance(data, dict) else None
                    title = err_obj.get("title", "Unknown Error") if isinstance(err_obj, dict) else "Unknown Error"
                    detail = err_obj.get("detail", "") if isinstance(err_obj, dict) else ""
                    LOGGER.error(
                        "QWeather API Error: %s (URL: %s) | qweather_code=%s | title=%s | detail=%s",
                        resp.status, url, qw_code, title, detail,
                    )
                    return {
                        "code": str(resp.status),
                        "http_status": resp.status,
                        "error_detail": f"{title} {detail}".strip() or "Unknown Error",
                    }
                
                return data 
        except asyncio.TimeoutError:
            LOGGER.debug("QWeather API 请求超时: %s", endpoint)
            raise
        except Exception as err:
            LOGGER.error("QWeather API 连接失败: %s", err)
            raise
        
    # --- 城市搜索 (全球) ---
    async def city_lookup(self, location: str, lang: str):
        """城市搜索: 全球范围，支持名称、ID 或 坐标 (语言跟随 HA 设置)."""
        return await self.request("v2", "city/lookup", {"location": location, "lang": lang})

    # --- 天气 API V1 (RESTful 风格，1km 分辨率，全球覆盖；v7 将于 2027-08-01 停服) ---
    async def get_weather_now(self, lat: str, lon: str, lang: str):
        """实时天气 V1: /weather/v1/current/{lat}/{lon}."""
        return await self.request(
            "weather/v1", "current/{lat}/{lon}",
            {"lat": lat, "lon": lon, "lang": lang}
        )

    async def get_forecast(self, lat: str, lon: str, days: int, lang: str):
        """每日预报 V1: /weather/v1/daily/{lat}/{lon} (days 支持 1-10，默认 7)."""
        return await self.request(
            "weather/v1", "daily/{lat}/{lon}",
            {"lat": lat, "lon": lon, "days": days, "lang": lang}
        )

    async def get_hourly(self, lat: str, lon: str, hours: int, lang: str):
        """逐小时预报 V1: /weather/v1/hourly/{lat}/{lon} (hours 支持 1-240，默认 24)."""
        return await self.request(
            "weather/v1", "hourly/{lat}/{lon}",
            {"lat": lat, "lon": lon, "hours": hours, "lang": lang}
        )

    # --- 空气质量与预警 (V1 强制坐标路径) ---
    async def get_air_v1(self, lat: str, lon: str, lang: str):
        """V1 专业空气质量."""
        return await self.request("airquality/v1", "current/{lat}/{lon}", {"lat": lat, "lon": lon, "lang": lang})

    async def get_warning_v1(self, lat: str, lon: str, lang: str):
        """V1 气象预警."""
        return await self.request("weatheralert/v1", "current/{lat}/{lon}", {"lat": lat, "lon": lon, "localTime": "true", "lang": lang})

    # ---辅助数据 ---
    async def get_indices(self, lat: str, lon: str, lang: str):
        """获取生活指数."""
        return await self.request("v7", "indices/1d", {"location": f"{lon},{lat}", "type": "0", "lang": lang})

    async def get_minutely(self, lat: str, lon: str, lang: str):
        """获取分钟级降水."""
        return await self.request("v7", "minutely/5m", {"location": f"{lon},{lat}", "lang": lang})