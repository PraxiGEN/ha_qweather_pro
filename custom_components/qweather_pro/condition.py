"""和风天气状态码与 Home Assistant 天气状态的对应关系."""
from __future__ import annotations

from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_EXCEPTIONAL,
    ATTR_CONDITION_FOG,
    ATTR_CONDITION_HAIL,
    ATTR_CONDITION_LIGHTNING,
    ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_POURING,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SNOWY_RAINY,
    ATTR_CONDITION_SUNNY,
    ATTR_CONDITION_WINDY,
)

# 和风天气代码映射表
# 官方参考: https://dev.qweather.com/docs/resource/icons/
CONDITION_MAP: dict[str, str] = {
    # 晴天与阴云
    "100": ATTR_CONDITION_SUNNY,           # 晴
    "101": ATTR_CONDITION_PARTLYCLOUDY,    # 多云
    "102": ATTR_CONDITION_CLOUDY,          # 少云 -> HA 阴
    "103": ATTR_CONDITION_PARTLYCLOUDY,    # 晴间多云
    "104": ATTR_CONDITION_CLOUDY,          # 阴
    
    # 夜间特殊状态
    "150": ATTR_CONDITION_CLEAR_NIGHT,     # 晴 (夜)
    "151": ATTR_CONDITION_CLOUDY,          # 多云 (夜)
    "152": ATTR_CONDITION_CLOUDY,          # 少云 (夜)
    "153": ATTR_CONDITION_PARTLYCLOUDY,    # 晴间多云 (夜)
    "154": ATTR_CONDITION_CLOUDY,          # 阴 (夜)

    # 雨
    "300": ATTR_CONDITION_RAINY,           # 阵雨
    "301": ATTR_CONDITION_RAINY,           # 强阵雨
    "302": ATTR_CONDITION_LIGHTNING_RAINY, # 雷阵雨
    "303": ATTR_CONDITION_LIGHTNING_RAINY, # 强雷阵雨
    "304": ATTR_CONDITION_HAIL,            # 雷阵雨伴有冰雹
    "305": ATTR_CONDITION_RAINY,           # 小雨
    "306": ATTR_CONDITION_RAINY,           # 中雨
    "307": ATTR_CONDITION_POURING,         # 大雨
    "308": ATTR_CONDITION_POURING,         # 极端降雨
    "309": ATTR_CONDITION_RAINY,           # 毛毛雨
    "310": ATTR_CONDITION_POURING,         # 暴雨
    "311": ATTR_CONDITION_POURING,         # 大暴雨
    "312": ATTR_CONDITION_POURING,         # 特大暴雨
    "313": ATTR_CONDITION_RAINY,           # 冻雨
    "314": ATTR_CONDITION_RAINY,           # 小到中雨
    "315": ATTR_CONDITION_RAINY,           # 中到大雨
    "316": ATTR_CONDITION_POURING,         # 大到暴雨
    "317": ATTR_CONDITION_POURING,         # 暴雨到大暴雨
    "318": ATTR_CONDITION_POURING,         # 大暴雨到特大暴雨
    "350": ATTR_CONDITION_RAINY,           # 阵雨
    "351": ATTR_CONDITION_POURING,         # 强阵雨
    "399": ATTR_CONDITION_RAINY,           # 雨

    # 雪
    "400": ATTR_CONDITION_SNOWY,           # 小雪
    "401": ATTR_CONDITION_SNOWY,           # 中雪
    "402": ATTR_CONDITION_SNOWY,           # 大雪
    "403": ATTR_CONDITION_SNOWY,           # 暴雪
    "404": ATTR_CONDITION_SNOWY_RAINY,     # 雨夹雪
    "405": ATTR_CONDITION_SNOWY_RAINY,     # 雨雪天气
    "406": ATTR_CONDITION_SNOWY_RAINY,     # 阵雨夹雪
    "407": ATTR_CONDITION_SNOWY,           # 阵雪
    "408": ATTR_CONDITION_SNOWY,           # 小到中雪
    "409": ATTR_CONDITION_SNOWY,           # 中到大雪
    "410": ATTR_CONDITION_SNOWY,           # 大到暴雪
    "456": ATTR_CONDITION_SNOWY_RAINY,     # 阵雨夹雪
    "457": ATTR_CONDITION_SNOWY,           # 阵雪
    "499": ATTR_CONDITION_SNOWY,           # 雪

    # 雾/霾/沙尘
    "500": ATTR_CONDITION_FOG,             # 薄雾
    "501": ATTR_CONDITION_FOG,             # 雾
    "502": ATTR_CONDITION_FOG,             # 霾
    "503": ATTR_CONDITION_EXCEPTIONAL,     # 扬沙
    "504": ATTR_CONDITION_EXCEPTIONAL,     # 浮尘
    "507": ATTR_CONDITION_EXCEPTIONAL,     # 沙尘暴
    "508": ATTR_CONDITION_EXCEPTIONAL,     # 强沙尘暴
    "509": ATTR_CONDITION_FOG,             # 浓雾
    "510": ATTR_CONDITION_FOG,             # 强浓雾
    "511": ATTR_CONDITION_FOG,             # 中度霾
    "512": ATTR_CONDITION_FOG,             # 重度霾
    "513": ATTR_CONDITION_FOG,             # 严重霾
    "514": ATTR_CONDITION_FOG,             # 大雾
    "515": ATTR_CONDITION_FOG,             # 特强浓雾

    # 其它
    "900": ATTR_CONDITION_EXCEPTIONAL,     # 热
    "901": ATTR_CONDITION_EXCEPTIONAL,     # 冷
    "999": ATTR_CONDITION_EXCEPTIONAL,     # 未知
}
