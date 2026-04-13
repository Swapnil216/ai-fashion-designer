import requests
from datetime import datetime


def get_event_weather(location_query, start_time, end_time):
    """Fetches real 'feels like' weather data tailored strictly to the exact street coordinates."""
    try:
        headers = {'User-Agent': 'LocalAIStylist/1.0'}
        geo_url = f"https://nominatim.openstreetmap.org/search?q={location_query}&format=json&limit=1"
        geo_response = requests.get(geo_url, headers=headers).json()

        if not geo_response:
            raise ValueError(f"Location '{location_query}' not found.")

        lat = geo_response[0]['lat']
        lon = geo_response[0]['lon']

        display_parts = geo_response[0]['display_name'].split(",")
        actual_location = ", ".join(display_parts[0:3]).strip()

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=apparent_temperature&timezone=auto"
        weather_data = requests.get(weather_url).json()

        times = weather_data['hourly']['time']
        temps = weather_data['hourly']['apparent_temperature']

        start_dt = datetime.fromisoformat(start_time.split("+")[0].replace("Z", ""))
        end_dt = datetime.fromisoformat(end_time.split("+")[0].replace("Z", ""))

        event_temps = []
        for t_str, temp in zip(times, temps):
            t_dt = datetime.fromisoformat(t_str)
            if start_dt.replace(minute=0, second=0) <= t_dt <= end_dt.replace(minute=59, second=59):
                if temp is not None:
                    event_temps.append(temp)

        if not event_temps:
            return {
                "max_temp": 20, "min_temp": 20, "trend": "stable",
                "desc": f"Exact hourly data unavailable for {actual_location}."
            }

        max_temp = max(event_temps)
        min_temp = min(event_temps)
        start_temp = event_temps[0]
        end_temp = event_temps[-1]

        if start_temp > end_temp:
            trend = "cooling down"
        elif end_temp > start_temp:
            trend = "warming up"
        else:
            trend = "staying stable"

        return {
            "max_temp": max_temp,
            "min_temp": min_temp,
            "trend": trend,
            "desc": f"At {actual_location}, it will feel like {start_temp}°C when you leave, {trend} to {end_temp}°C by the time you finish. (High: {max_temp}°C, Low: {min_temp}°C)."
        }

    except Exception as e:
        print(f"Weather/Geocoding Error: {e}")
        return {"max_temp": 20, "min_temp": 15, "trend": "cooling down", "desc": "Clear (Fallback - API Error)"}