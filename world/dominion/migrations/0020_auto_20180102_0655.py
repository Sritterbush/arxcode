# -*- coding: utf-8 -*-
# Generated by Django 1.11.8 on 2018-01-02 06:55
from __future__ import unicode_literals

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


def fix_domains(apps, schema_editor):
    Domain = apps.get_model("dominion", "Domain")
    MapLocation = apps.get_model("dominion", "MapLocation")
    for domain in Domain.objects.filter(land__isnull=False):
        location = MapLocation()
        location.land = domain.land
        location.save()
        domain.location = location
        domain.save()


def fix_plotrooms(apps, schema_editor):
    PlotRoom = apps.get_model("dominion", "PlotRoom")
    MapLocation = apps.get_model("dominion", "MapLocation")
    for room in PlotRoom.objects.filter(land__isnull=False):
        location = MapLocation()
        location.land = room.land
        location.save()
        room.location = location
        room.save()


def fix_landmarks(apps, schema_editor):
    Landmark = apps.get_model("dominion", "Landmark")
    MapLocation = apps.get_model("dominion", "MapLocation")
    for landmark in Landmark.objects.filter(land__isnull=True):
        location = MapLocation()
        location.land = landmark.land
        location.save()
        landmark.location = location
        landmark.save()


def fix_shardhavens(apps, schema_editor):
    Shardhaven = apps.get_model("dominion", "Shardhaven")
    MapLocation = apps.get_model("dominion", "MapLocation")
    for haven in Shardhaven.objects.filter(land__isnull=True):
        location = MapLocation()
        location.land = haven.land
        location.save()
        haven.location = location
        haven.save()


class Migration(migrations.Migration):

    dependencies = [
        ('dominion', '0019_auto_20171228_0839'),
    ]

    operations = [
        migrations.CreateModel(
            name='MapLocation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, max_length=80, null=True)),
                ('x_coord', models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MaxValueValidator(9)])),
                ('y_coord', models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MaxValueValidator(9)])),
                ('land', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, related_name='locations',
                                           to='dominion.Land', blank=True, null=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='domain',
            name='location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='domains', to='dominion.MapLocation'),
        ),
        migrations.AddField(
            model_name='landmark',
            name='location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='landmarks', to='dominion.MapLocation'),
        ),
        migrations.AddField(
            model_name='plotroom',
            name='location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='plot_rooms', to='dominion.MapLocation'),
        ),
        migrations.AddField(
            model_name='shardhaven',
            name='location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='shardhavens', to='dominion.MapLocation'),
        ),

        migrations.RunPython(fix_domains),
        migrations.RunPython(fix_plotrooms),
        migrations.RunPython(fix_landmarks),
        migrations.RunPython(fix_shardhavens)
    ]