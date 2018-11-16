# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2018-11-12 22:59
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('character', '0029_auto_20181111_2007'),
        ('exploration', '0014_shardhavenobstacle_haven_types'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShardhavenObstacleClue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('clue', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='character.Clue')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.RemoveField(
            model_name='shardhavenobstacle',
            name='clue',
        ),
        migrations.AddField(
            model_name='shardhavenobstacleroll',
            name='override',
            field=models.BooleanField(default=False, help_text=b'Should succeeding on this roll make the obstacle open to everyone else?', verbose_name=b'Override on Success'),
        ),
        migrations.AlterField(
            model_name='shardhavenobstacle',
            name='obstacle_type',
            field=models.PositiveSmallIntegerField(choices=[(0, b'Pass a Dice Check'), (1, b'Possess Any Associated Clue'), (2, b'Possess All Associated Clues')]),
        ),
        migrations.AddField(
            model_name='shardhavenobstacleclue',
            name='obstacle',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='clues', to='exploration.ShardhavenObstacle'),
        ),
    ]