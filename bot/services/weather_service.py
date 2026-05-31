import httpx
import logging
from bot import config

log = logging.getLogger(__name__)

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"


async def get_weather() -> dict | None:
    params = {
        "q": config.OPENWEATHER_CITY,
        "appid": config.OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "pt_br",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            return {
                "city": data["name"],
                "temp": round(data["main"]["temp"]),
                "feels_like": round(data["main"]["feels_like"]),
                "description": data["weather"][0]["description"].capitalize(),
                "humidity": data["main"]["humidity"],
                "icon": data["weather"][0]["icon"],
            }
    except Exception as e:
        log.error("weather_service error: %s", e)
        return None
