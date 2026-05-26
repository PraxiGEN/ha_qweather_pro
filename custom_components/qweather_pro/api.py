"""和风天气 API 客户端."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import jwt
from aiohttp import ClientSession
from cryptography.hazmat.primitives import serialization

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
        host: str = "api.qweather.com"
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
            private_key_obj = serialization.load_pem_private_key(
                self.private_key.encode('utf-8'), password=None
            )
            now_ts = int(time.time())
            payload = {
                'iat': now_ts - 30, # 提前30秒防止服务器时钟漂移
                'exp': now_ts + 900,
                'sub': self.project_id
            }
            return jwt.encode(
                payload, 
                private_key_obj, 
                algorithm='EdDSA', 
                headers={'kid': self.key_id}
            )
        except Exception as err:
            LOGGER.error("QWeather JWT 签名生成失败: %s", err)
            return None

    async def request(self, version_path: str, endpoint: str, params: dict[str, Any], custom_host: str | None = None) -> dict[str, Any]:
        """统一底层异步请求方法."""
        # 移除 params 中的空值
        params = {k: v for k, v in params.items() if v is not None}
        
        target_host = custom_host or self.host
        url = f"https://{target_host}/{version_path}/{endpoint}"
        headers = {"User-Agent": "HomeAssistant-QWeatherPro/2.0"}

        if self.use_token:
            token = self._generate_jwt()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        else:
            params["key"] = self.api_key

        try:
            # 2026 规范：必须使用 asyncio.timeout 包装，防止网络挂起
            async with asyncio.timeout(15):
                resp = await self.session.get(url, params=params, headers=headers)
                if resp.status != 200:
                    LOGGER.error("QWeather API 响应异常: HTTP %s (URL: %s)", resp.status, url)
                    return {"code": str(resp.status)}
                
                return await resp.json()
        except asyncio.TimeoutError:
            LOGGER.debug("QWeather API 请求超时: %s", endpoint)
            return {"code": "timeout"}
        except Exception as err:
            LOGGER.error("QWeather API 连接失败: %s", err)
            return {"code": "500", "msg": str(err)}

    # --- 业务逻辑快捷方法 ---

    async def get_weather_now(self, location: str, api_type: str = "weather"):
        """获取实况天气."""
        return await self.request("v7", f"{api_type}/now", {"location": location})

    async def get_forecast(self, location: str, days: str, api_type: str = "weather"):
        """获取逐日预报."""
        return await self.request("v7", f"{api_type}/{days}", {"location": location})

    async def get_hourly(self, location: str, hours: str, api_type: str = "weather"):
        """获取逐小时预报."""
        return await self.request("v7", f"{api_type}/{hours}", {"location": location})

    async def get_air_now(self, location: str):
        """获取空气质量实况."""
        return await self.request("v7", "air/now", {"location": location})

    async def get_air_v1(self, location: str):
        """获取 V1 专业级实时空气质量."""
        try:
            coords = [c.strip() for k in location.split(',') for c in k.split()]
            lon, lat = coords[0], coords[1]
            # 路径: /airquality/v1/current/{lat}/{lon}
            endpoint = f"current/{lat}/{lon}"
            return await self.request("airquality/v1", endpoint, {})
        except Exception:
            return {"code": "400"}

    async def get_indices(self, location: str):
        """获取生活指数."""
        return await self.request("v7", "indices/1d", {"location": location, "type": "0"})

    async def get_minutely(self, location: str):
        """获取分钟级降水."""
        return await self.request("v7", "minutely/5m", {"location": location})

    async def get_warning_v1(self, location: str):
        """获取天气预警 (处理 V1 路径参数)."""
        try:
            # 坐标清洗：支持 "lon,lat"
            coords = [c.strip() for k in location.split(',') for c in k.split()]
            if len(coords) < 2:
                return {"code": "400", "msg": "Warning API requires lon,lat"}
            
            lon, lat = coords[0], coords[1]
            endpoint = f"current/{lat}/{lon}"
            return await self.request("weatheralert/v1", endpoint, {"localTime": "true"})
        except Exception:
            return {"code": "400"}

    async def city_lookup(self, location: str):
        """城市搜索/逆地理编码."""
        # 修正：直接传递 custom_host 而非修改 self.host，保证线程安全
        return await self.request(
            "v2", 
            "city/lookup", 
            {"location": location, "range": "cn"}, 
            custom_host="geoapi.qweather.com"
        )