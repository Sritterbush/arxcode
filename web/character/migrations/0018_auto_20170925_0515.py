# -*- coding: utf-8 -*-
# Generated by Django 1.9.13 on 2017-09-25 05:15
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('character', '0017_remove_theory_known_by'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='theory',
            name='can_edit',
        ),
        migrations.RemoveField(
            model_name='theory',
            name='known_by2',
        ),
        migrations.AddField(
            model_name='theory',
            name='known_by',
            field=models.ManyToManyField(blank=True, null=True, related_name='known_theories',
                                         through='character.TheoryPermissions', to=settings.AUTH_USER_MODEL),
        ),
    ]
