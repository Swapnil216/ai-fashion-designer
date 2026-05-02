import requests
from datetime import datetime


def get_event_weather(location_string, start_time_iso, end_time_iso):
    """Fetches hourly weather and slices it to the user's specific event window."""
    print(f"🌍 Fetching micro-climate for: {location_string}...")

    headers = {'User-Agent': 'Local-AI-Stylist-App/1.0'}
    geocode_url = f"https://nominatim.openstreetmap.org/search?q={location_string}&format=json&limit=1"

    try:
        #Geocoding
        geo_response = requests.get(geocode_url, headers=headers).json()
        if not geo_response:
            print("⚠️ Geocoding failed. Falling back to default Berlin coordinates.")
            lat, lon = "52.5200", "13.4050"
        else:
            lat = geo_response[0]['lat']
            lon = geo_response[0]['lon']

        #Hourly Weather Fetch
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation_probability,weather_code&timezone=auto"
        response = requests.get(weather_url)

        # If the API throws an error, this will catch it and tell us why
        response.raise_for_status()
        data = response.json()

        #Parse Dates
        try:
            start_dt = datetime.fromisoformat(start_time_iso).replace(minute=0, second=0, microsecond=0)
            end_dt = datetime.fromisoformat(end_time_iso).replace(minute=0, second=0, microsecond=0)
        except ValueError:
            start_dt = datetime.now().replace(minute=0, second=0, microsecond=0)
            end_dt = start_dt

        api_times = [datetime.fromisoformat(t) for t in data['hourly']['time']]
        valid_indices = [i for i, t in enumerate(api_times) if start_dt <= t <= end_dt]

        if not valid_indices:
            valid_indices = [0]

        window_temps = [data['hourly']['temperature_2m'][i] for i in valid_indices]
        window_probs = [data['hourly']['precipitation_probability'][i] for i in valid_indices]

        window_codes = [data['hourly']['weather_code'][i] for i in valid_indices]

        #Calculate Event Metrics
        max_t = max(window_temps)
        min_t = min(window_temps)
        max_rain_chance = max(window_probs)
        will_rain = max_rain_chance > 30
        worst_code = max(window_codes)

        return {
            "max_temp": max_t,
            "min_temp": min_t,
            "desc": translate_weather_code(worst_code),
            "will_rain": will_rain,
            "rain_prob": max_rain_chance
        }

    except requests.exceptions.HTTPError as http_err:
        print(f"⚠️ Open-Meteo API Error: {http_err}")
        return {"max_temp": 20, "min_temp": 15, "desc": "Clear (Fallback - HTTP Error)", "will_rain": False,
                "rain_prob": 0}
    except Exception as e:
        print(f"⚠️ Weather Engine Error: {e}")
        return {"max_temp": 20, "min_temp": 15, "desc": "Clear (Fallback - System Error)", "will_rain": False,
                "rain_prob": 0}

def translate_weather_code(code):
    """Translates standard WMO weather codes into readable text."""
    if code <= 1: return "Clear sky"
    if code <= 3: return "Partly cloudy"
    if code <= 49: return "Foggy"
    if code <= 69: return "Rainy"
    if code <= 79: return "Snowy"
    if code <= 99: return "Thunderstorms"
    return "Unknown"