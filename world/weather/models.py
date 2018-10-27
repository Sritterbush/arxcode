from evennia.typeclasses.models import SharedMemoryModel
from django.db import models


class WeatherType(SharedMemoryModel):

    name = models.CharField('Weather Name', max_length=25)
    gm_notes = models.TextField('GM Notes', blank=True, null=True)


class WeatherEmit(SharedMemoryModel):

    weather = models.ForeignKey(WeatherType, related_name='emits')

    at_night = models.BooleanField('Night', default=True)
    at_morning = models.BooleanField('Morning', default=True)
    at_afternoon = models.BooleanField('Afternoon', default=True)
    at_evening = models.BooleanField('Evening', default=True)

    in_summer = models.BooleanField('Summer', default=True)
    in_fall = models.BooleanField('Fall', default=True)
    in_winter = models.BooleanField('Winter', default=True)
    in_spring = models.BooleanField('Spring', default=True)

    intensity_min = models.PositiveSmallIntegerField('Min Intensity', default=1)
    intensity_max = models.PositiveSmallIntegerField('Max Intensity', default=10)
    weight = models.PositiveIntegerField('Weight')
    text = models.TextField('Emit', blank=False, null=False)
    gm_notes = models.TextField('GM Notes', blank=True, null=True)


def build_defaults():
    """
    This builds some very basic defaults so we at least have some weather.
    """
    clear_type = WeatherType(name='Clear')
    storm_type = WeatherType(name='Stormy/Raining')
    snow_type = WeatherType(name='Snowing')
    fog_type = WeatherType(name='Fog')

    WeatherType.objects.bulk_create([clear_type, storm_type, snow_type, fog_type])

    emit1 = WeatherEmit(
        weather=clear_type,
        text="The sky is clear and cloudless, the sun shining brightly."
    )

    emit2 = WeatherEmit(
        weather=storm_type,
        text="Dark clouds cover the sky, thunder rumbling in the distance, as rain threatens to fall."
    )

    emit3 = WeatherEmit(
        weather=snow_type,
        text="Snow falls gently from the sky, gathering in white piles on the ground."
    )

    emit4 = WeatherEmit(
        weather=fog_type,
        text="Fog clings low to the ground, turning the world into dimly seen outlines."
    )

    WeatherEmit.objects.bulk_create([emit1, emit2, emit3, emit4])