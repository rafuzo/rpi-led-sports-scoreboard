from setup.session_setup import session
from utils import data_utils
from datetime import datetime as dt


# Cache of the last successful API response. Weather changes slowly, so avoid hitting the API on every display loop.
_cache = {
    'key': None,         # (latitude, longitude, units) the cached data was fetched for.
    'fetched_at': None,  # When the cached data was fetched.
    'data': None         # The processed weather dict.
}
CACHE_MINUTES = 10

# Mapping of WMO weather codes (returned by Open-Meteo) to the icon set used by the weather scene.
WMO_CODE_ICONS = {
    'clear':         [0, 1],
    'partly_cloudy': [2],
    'cloudy':        [3],
    'fog':           [45, 48],
    'rain':          [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82],
    'snow':          [71, 73, 75, 77, 85, 86],
    'storm':         [95, 96, 99]
}


def get_weather():
    """ Loads current conditions and daily forecast for the location set in config.yaml.
    Uses the free Open-Meteo API (no key required). Results are cached for CACHE_MINUTES.

    Returns:
        dict or None: Dict of current conditions and daily forecast, or None if the API call fails.
    """

    # Load weather config (location + units) from config.yaml.
    weather_config = data_utils.read_yaml('config.yaml')['weather']
    latitude = weather_config['latitude']
    longitude = weather_config['longitude']
    units = weather_config.get('units', 'imperial')

    # Return cached data if it's still fresh and for the same location/units.
    cache_key = (latitude, longitude, units)
    if (
        _cache['data'] is not None
        and _cache['key'] == cache_key
        and (dt.now() - _cache['fetched_at']).total_seconds() < CACHE_MINUTES * 60
    ):
        return _cache['data']

    # Call the Open-Meteo forecast API. Any failure (network, unexpected response) results in None so the scene can skip cleanly.
    try:
        url = (
            'https://api.open-meteo.com/v1/forecast'
            f'?latitude={latitude}&longitude={longitude}'
            '&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day'
            '&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max'
            '&timezone=auto&forecast_days=4'
        )
        if units == 'imperial':
            url += '&temperature_unit=fahrenheit&wind_speed_unit=mph'

        weather_response = session.get(url=url, timeout=15)
        weather_json = weather_response.json()

        # Build the current conditions dict.
        current_json = weather_json['current']
        weather = {
            'retrieved_on': dt.now().astimezone(),
            'current': {
                'temp': round(current_json['temperature_2m']),
                'feels_like': round(current_json['apparent_temperature']),
                'humidity': current_json['relative_humidity_2m'],
                'wind': round(current_json['wind_speed_10m']),
                'icon': icon_for_wmo_code(current_json['weather_code']),
                'is_day': current_json['is_day'] == 1
            },
            'daily': []
        }

        # Build the daily forecast list. Index 0 is today.
        daily_json = weather_json['daily']
        for i, date_str in enumerate(daily_json['time']):
            date = dt.strptime(date_str, '%Y-%m-%d').date()
            weather['daily'].append({
                'date': date,
                'day_abrv': date.strftime('%a').upper()[:2],  # 'MO', 'TU', etc.
                'hi': round(daily_json['temperature_2m_max'][i]),
                'lo': round(daily_json['temperature_2m_min'][i]),
                'icon': icon_for_wmo_code(daily_json['weather_code'][i]),
                'precip_pct': daily_json['precipitation_probability_max'][i]
            })

    except Exception as e:
        print(f'Weather data fetch failed: {e}')
        return None

    # Update the cache and return.
    _cache['key'] = cache_key
    _cache['fetched_at'] = dt.now()
    _cache['data'] = weather

    return weather


def icon_for_wmo_code(code):
    """ Maps a WMO weather code to an icon name used by the weather scene.

    Args:
        code (int): WMO weather code as returned by Open-Meteo.

    Returns:
        str: Icon name. Falls back to 'cloudy' for unmapped codes.
    """

    for icon, codes in WMO_CODE_ICONS.items():
        if code in codes:
            return icon

    return 'cloudy'
