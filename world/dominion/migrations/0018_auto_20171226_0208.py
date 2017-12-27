# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2017-12-26 02:08
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('character', '0022_auto_20171226_0208'),
        ('dominion', '0017_auto_20171217_0306'),
    ]

    operations = [
        migrations.CreateModel(
            name='Landmark',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=32)),
                ('description', models.TextField(max_length=2048)),
                ('landmark_type', models.PositiveSmallIntegerField(choices=[(0, b'Unknown'), (1, b'Faith'), (2, b'Cultural'), (3, b'Historical')], default=0)),
                ('land', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='landmarks', to='dominion.Land')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Shardhaven',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=78)),
                ('description', models.TextField(max_length=4096)),
                ('required_clue_value', models.IntegerField(default=0)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ShardhavenClue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('required', models.BooleanField(default=False)),
                ('clue', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='related_shardhavens', to='character.Clue')),
                ('shardhaven', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='related_clues', to='dominion.Shardhaven')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ShardhavenDiscovery',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('discovered_on', models.DateTimeField(blank=True, null=True)),
                ('discovery_method', models.PositiveSmallIntegerField(choices=[(0, b'Unknown'), (1, b'Exploration'), (2, b'Clues')], default=0)),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shardhaven_discoveries', to='dominion.PlayerOrNpc')),
                ('shardhaven', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='discoveries', to='dominion.Shardhaven')),
            ],
            options={
                'verbose_name_plural': 'Shardhaven Discoveries',
            },
        ),
        migrations.CreateModel(
            name='ShardhavenType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=32)),
                ('description', models.TextField(max_length=2048)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='shardhaven',
            name='discovered_by',
            field=models.ManyToManyField(blank=True, related_name='discovered_shardhavens', through='dominion.ShardhavenDiscovery', to='dominion.PlayerOrNpc'),
        ),
        migrations.AddField(
            model_name='shardhaven',
            name='haven_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='havens', to='dominion.ShardhavenType'),
        ),
        migrations.AddField(
            model_name='shardhaven',
            name='land',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='shardhavens', to='dominion.Land'),
        ),
        migrations.AddField(
            model_name='plotroom',
            name='shardhaven_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tilesets', to='dominion.ShardhavenType'),
        ),
    ]