"""QWeather (和风天气) API 客户端."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import jwt
from aiohttp import ClientSession
from cryptography.hazmat.primitives import serialization
from tenacity import retry, stop_after_attempt, wait_exponential

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
        host: str | None = None
    ) -> None:
        self.session = session
        self.api_key = api_key
        self.use_token = use_token
        self.project_id = project_id
        self.key_id = key_id
        self.private_key = private_key
        self.host = host

    def _generate_jwt(self) -> str | None:
        """生成符合 EdDSA 算法的 JWT 签名."""
        try:
            if not self.private_key:
                return None
            
            # 加载 Ed25519 私钥
            private_key_obj = serialization.load_pem_private_key(
                self.private_key.encode('utf-8'), password=None
            )
            
            now_ts = int(time.time())
            # Payload: 仅包含 sub, iat, exp。移除所有默认字段。
            payload = {
                'sub': self.project_id,
                'iat': now_ts - 30,   # 解决服务器时钟不同步
                'exp': now_ts + 900    # 有效期 15 分钟
            }
            
            # Header: 显式指定 alg 和 kid
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
        retry_error_callback=lambda retry_state: LOGGER.error(
            "和风天气 API 请求在 %s 次尝试后彻底失败: %s",
            retry_state.attempt_number, retry_state.outcome.exception()
        )
    )

    async def request(self, version_path: str, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """统一底层异步请求方法."""

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
            if token: headers["Authorization"] = f"Bearer {token}"
        else:
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
                    LOGGER.error("QWeather API Error: %s (URL: %s)", resp.status, url)
                    return {
                        "code": str(resp.status),
                        "http_status": resp.status,
                        "error_detail": data.get("error", {}).get("title", "Unknown Error")
                    }
                
                return data 
        except asyncio.TimeoutError:
            LOGGER.debug("QWeather API 请求超时: %s", endpoint)
            raise # 触发重试
        except Exception as err:
            LOGGER.error("QWeather API 连接失败: %s", err)
            raise # 触发重试

    # --- 城市搜索 ---
    async def city_lookup(self, location: str, lang: str):
        """城市搜索: 支持名称、ID 或 坐标."""
        return await self.request("v2", "city/lookup", {"location": location, "range": "cn", "lang": lang})

    # --- 标准天气 API (基于观测站) ---
    async def get_weather_now(self, lat: str, lon: str, lang: str):
        """获取实况天气."""
        return await self.request("v7", "weather/now", {"location": f"{lon},{lat}", "lang": lang})

    async def get_forecast(self, lat: str, lon: str, days: str, lang: str):
        """获取逐日预报 (days 支持 3d/7d/10d/15d/30d)."""
        return await self.request("v7", f"weather/{days}", {"location": f"{lon},{lat}", "lang": lang})

    async def get_hourly(self, lat: str, lon: str, hours: str, lang: str):
        """获取逐小时预报 (hours 支持 24h/72h/168h)."""
        return await self.request("v7", f"weather/{hours}", {"location": f"{lon},{lat}", "lang": lang})

    # --- 格点天气 API (基于数值模式，高精度坐标) ---
    async def get_grid_weather_now(self, lat: str, lon: str, lang: str):
        """格点实况天气."""
        return await self.request("v7", "grid-weather/now", {"location": f"{lon},{lat}", "lang": lang})

    async def get_grid_forecast(self, lat: str, lon: str, days: str, lang: str):
        """格点每日预报 (支持 3d/7d)."""
        return await self.request("v7", f"grid-weather/{days}", {"location": f"{lon},{lat}", "lang": lang})

    async def get_grid_hourly(self, lat: str, lon: str, hours: str, lang: str):
        """格点逐小时预报 (支持 24h/72h)."""
        return await self.request("v7", f"grid-weather/{hours}", {"location": f"{lon},{lat}", "lang": lang})

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