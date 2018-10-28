from evennia.server.models import ServerConfig
from server.utils.arx_utils import ArxCommand
from . import utils
from .models import WeatherType
from typeclasses.scripts import gametime


class CmdAdminWeather(ArxCommand):
    """
    Provides administration for the weather system.

    Usage:
        @admin_weather
        @admin_weather/advance
        @admin_weather/announce
        @admin_weather/lock
        @admin_weather/unlock
        @admin_weather/set [custom weather emit]

    """

    key = "@admin_weather"
    locks = "cmd:perm(Wizards)"
    category = "Admin"

    def func(self):

        if "advance" in self.switches:
            if ServerConfig.objects.conf('weather_locked', default=False):
                self.msg("Weather is currently locked, and cannot be advanced!")
                return

            weather, intensity = utils.advance_weather()
            weatherobj = WeatherType.objects.get(pk=weather)
            self.msg("Current weather is now {} ({}), intensity {}.  "
                     "Remember to {}/announce if you want players to know.".format(weatherobj.name, weather, intensity, self.cmdstring))
            return

        if "announce" in self.switches:
            emit = utils.choose_current_weather()
            utils.announce_weather(emit)
            return

        if "set" in self.switches:
            if self.args:
                ServerConfig.objects.conf('weather_custom', value=self.args)
                self.msg('Custom weather emit set.  Remember to {}/announce if you want the players to know.'
                         .format(self.cmdstring))
                return
            else:
                ServerConfig.objects.conf('weather_custom', delete=True)
                self.msg('Custom weather message cleared.  Remember to {}/announce '
                         'if you want the players to see a new weather emit.'.format(self.cmdstring))
                return

        if "lock" in self.switches:
            ServerConfig.objects.conf('weather_locked', value=True)
            self.msg("Weather is now locked and will not change.")
            return

        if "unlock" in self.switches:
            ServerConfig.objects.conf('weather_locked', delete=True)
            self.msg("Weather is now unlocked and will change again as normal.")
            return

        current_weather = utils.get_weather_type()
        target_weather = utils.get_weather_target_type()

        current_intensity = utils.get_weather_intensity()
        target_intensity = utils.get_weather_target_intensity()

        current_obj = WeatherType.objects.get(pk=current_weather)
        target_obj = WeatherType.objects.get(pk=target_weather)

        locked = ServerConfig.objects.conf('weather_locked', default=False)
        custom = ServerConfig.objects.conf('weather_custom', default=None)

        self.msg("\nWeather pattern is {} (intensity {}), moving towards {} (intensity {})."
                 .format(current_obj.name, current_intensity, target_obj.name, target_intensity))
        if custom:
            self.msg("However, weather currently is set to a custom value: " + custom)
        if locked:
            self.msg("And weather currently is locked, and will not change. {}/unlock to restore normal weather"
                     .format(self.cmdstring))


class CmdWeather(ArxCommand):
    """
    Displays the current weather conditions.

    Usage:
        weather

    This will show you the current time and weather.
    """
    key = "weather"
    locks = "cmd:all()"

    def func(self):
        season, time = gametime.get_time_and_season()
        pref = "an" if season == "autumn" else "a"
        weather = utils.get_last_emit()

        self.msg("It is {} {} {}. {}".format(pref, season, time, weather or ""))