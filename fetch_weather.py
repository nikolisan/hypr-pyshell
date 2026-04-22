import aiohttp
import asyncio
import logging

logger = logging.getLogger(__name__)


async def get_ip_info(session: aiohttp.ClientSession, retries: int = 3) -> dict:
    url = "https://ipinfo.io/json"
    logger.debug("Acquiring location for the users IP.")
    for attempt in range(retries):
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()

                lat = data["loc"].split(",")[0]
                lon = data["loc"].split(",")[1]

                logger.debug(f"IPinfo retrieved for {data['ip']}.")
                return {
                    "ip": data["ip"],
                    "location": f"{data['city']}, {data['country']}",
                    "lat": lat,
                    "lon": lon,
                }
        except Exception as err:
            if attempt < retries - 1:
                logger.debug(f"IPinfo: Retry attempt {attempt + 1}/{retries}: {err}")
                await asyncio.sleep(1)

    logger.error("Error fetchin ip info.")
    return {}


async def get_weather(lat: str, lon: str, session: aiohttp.ClientSession) -> dict:
    api_key = "874542aeea0c4841a04142640261404"
    url = f"https://api.weatherapi.com/v1/current.json?q={lat},{lon}&key={api_key}"
    async with session.get(url) as response:
        data = await response.json()

    return {
        "last_updated_epoch": data["current"]["last_updated_epoch"],
        "last_updated": data["current"]["last_updated"],
        "temp_c": data["current"]["temp_c"],
        "feelslike_c": data["current"]["feelslike_c"],
        "humidity": data["current"]["humidity"],
        "condition": data["current"]["condition"]["text"],
        "cloud": data["current"]["cloud"],
        "wind_kph": data["current"]["wind_kph"],
        "wind_dir": data["current"]["wind_dir"],
        "precip_mm": data["current"]["precip_mm"],
    }


async def fetch_data(city):
    logger.debug(f"Fetching data for {city}.")
    async with aiohttp.ClientSession() as session:
        ip_info = await get_ip_info(session)
        lat = ip_info["lat"]
        lon = ip_info["lon"]
        weather = await get_weather(lat, lon, session)

        return {"location": ip_info["location"], "weather": weather}


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
    data = asyncio.run(fetch_data(""))
    print(data)
