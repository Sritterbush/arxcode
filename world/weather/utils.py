from .models import WeatherType, WeatherEmit
from typeclasses.scripts import gametime
from evennia.server.models import ServerConfig
from random import randint


def weather_emits(weathertype, season=None, time=None, intensity=5):
    if not season:
        season, _ = gametime.get_time_and_season()

    if not time:
        _, time = gametime.get_time_and_season()

    qs = WeatherEmit.objects.filter(weather=weathertype)
    qs.filter(intensity_min__lte=intensity, intensity_max__gte=intensity)
    if season == 'spring':
        qs = qs.filter(in_spring=True)
    elif season == 'summer':
        qs = qs.filter(in_summer=True)
    elif season == 'fall':
        qs = qs.filter(in_fall=True)
    elif season == 'winter':
        qs = qs.filter(in_winter=True)

    if time == 'night':
        qs = qs.filter(at_night=True)
    elif time == 'morning':
        qs = qs.filter(at_morning=True)
    elif time == 'afternoon':
        qs = qs.filter(at_afternoon=True)
    elif time == 'night':
        qs = qs.filter(at_night=True)

    return qs


def pick_emit(weathertype, season=None, time=None, intensity=None):

    if weathertype is None:
        weathertype = ServerConfig.objects.conf('current_weather_type', default=1)

    if isinstance(weathertype, int):
        weathertype = WeatherType.objects.get(pk=weathertype)

    if not isinstance(weathertype, WeatherType):
        raise ValueError

    if intensity is None:
        intensity = ServerConfig.objects.conf('current_weather_intensity', default=5)

    emits = weather_emits(weathertype, season=season, time=time, intensity=intensity)

    if emits.count() == 0:
        return None

    if emits.count() == 1:
        return emits[0].text

    values = {}
    current_value = 0
    for emit in emits:
        values[current_value] = emit
        current_value += emit.weight

    picker = randint(0, current_value)
    last_value = 0
    result = None
    for key in values.keys():
        if key >= picker:
            result = values[last_value]
            continue

    if not result:
        result = emits.last()

    return result.text if result else None


def set_weather_type(value=1):
    ServerConfig.objects.set('current_weather_type', value)


def set_weather_intensity(value=5):
    ServerConfig.objects.set('current_weather_intensity', value)
