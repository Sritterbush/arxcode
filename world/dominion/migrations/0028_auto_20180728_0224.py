# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2018-07-28 02:24
"""
Migration where we'll be changing RPEvents a great deal to allow for org sponsorships. This will include
a data migration of existing PlayerOrNpc relationships to RPEvents - we want to preserve our list of hosts,
participants, and GMs. Praises were also changed from targeting a PlayerOrNpc to targeting an AssetOwner, so
that praises could be used on orgs.
"""
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
from django.db.models import F


def store_previous_target_asset_owners_in_temp_field(apps, schema_editor):
    """Stores all previous target's assetowners in the temporary field we created"""
    PraiseOrCondemn = apps.get_model("dominion", "PraiseOrCondemn")
    AssetOwner = apps.get_model("dominion", "AssetOwner")
    for ob in PraiseOrCondemn.objects.all():
        ob.temporary = ob.target.assets
        ob.save()


def switch_asset_owners_into_new_field(apps, schema_editor):
    """Updates PraiseOrCondemn's target to be the temporary assetowner field we set earlier"""
    PraiseOrCondemn = apps.get_model("dominion", "PraiseOrCondemn")
    PraiseOrCondemn.objects.update(target=F('temporary'))


def populate_participants(apps, schema_editor):
    """Converts hosts, gms, and participants into the new models"""
    Host = apps.get_model("dominion", "RPEvent_hosts")
    GM = apps.get_model("dominion", "RPEvent_gms")
    Participant = apps.get_model("dominion", "RPEvent_participants")
    RPEvent = apps.get_model("dominion", "RPEvent")
    PCEventParticipation = apps.get_model("dominion", "PCEventParticipation")
    parts = {}
    current_event = None
    for host in Host.objects.order_by('rpevent'):
        event = host.rpevent
        # the first host for each event is marked as the main host
        if event != current_event:
            current_event = event
            status = 0
        else:
            status = 1
        dompc = host.playerornpc
        parts[(event, dompc)] = PCEventParticipation(event=event, dompc=dompc, status=status, attended=True)
    for participant in Participant.objects.all():
        event = participant.rpevent
        dompc = participant.playerornpc
        if (event, dompc) not in parts:
            parts[(event, dompc)] = PCEventParticipation(event=event, dompc=dompc, status=2, attended=True)
    for gm in GM.objects.all():
        event = gm.rpevent
        dompc = gm.playerornpc
        if (event, dompc) in parts:
            parts[(event, dompc)].gm = True
        else:
            parts[(event, dompc)] = PCEventParticipation(event=event, dompc=dompc, status=1, gm=True, attended=True)
    PCEventParticipation.objects.bulk_create(parts.values())


class Migration(migrations.Migration):
    """Migration to add Org relationships to RPEvents"""
    dependencies = [
        ('dominion', '0027_honorific_propriety'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrgEventParticipation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('social', models.PositiveSmallIntegerField(default=0,
                                                            verbose_name=b'Social Resources spent by the Org Sponsor')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='PCEventParticipation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.PositiveSmallIntegerField(choices=[(0, b'Main Host'), (1, b'Host'), (2, b'Guest')],
                                                            default=2)),
                ('gm', models.BooleanField(default=False)),
                ('attended', models.BooleanField(default=False)),
                ('dompc', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                            related_name='event_participation', to='dominion.PlayerOrNpc')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AlterField(
            model_name='rpevent',
            name='celebration_tier',
            field=models.PositiveSmallIntegerField(blank=True,
                                                   choices=[(0, b'Small'), (1, b'Average'), (2, b'Refined'),
                                                            (3, b'Grand'), (4, b'Extravagant'), (5, b'Legendary')],
                                                   default=0),
        ),
        migrations.AlterField(
            model_name='rpevent',
            name='risk',
            field=models.PositiveSmallIntegerField(blank=True,
                                                   choices=[(0, b'No Risk'), (1, b'Minimal Risk'), (2, b'Low Risk'),
                                                            (3, b'Reduced Risk'), (4, b'Normal Risk'),
                                                            (5, b'Slightly Elevated Risk'),
                                                            (6, b'Moderately Elevated Risk'),
                                                            (7, b'Highly Elevated Risk'), (8, b'Very High Risk'),
                                                            (9, b'Extreme Risk'), (10, b'Suicidal Risk')], default=4),
        ),
        migrations.AddField(
            model_name='pceventparticipation',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pc_event_participation',
                                    to='dominion.RPEvent'),
        ),
        migrations.AddField(
            model_name='orgeventparticipation',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='org_event_participation',
                                    to='dominion.RPEvent'),
        ),
        migrations.AddField(
            model_name='orgeventparticipation',
            name='org',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='event_participation',
                                    to='dominion.Organization'),
        ),
        migrations.AddField(
            model_name='rpevent',
            name='dompcs',
            field=models.ManyToManyField(blank=True, related_name='events', through='dominion.PCEventParticipation',
                                         to='dominion.PlayerOrNpc'),
        ),
        migrations.AddField(
            model_name='rpevent',
            name='orgs',
            field=models.ManyToManyField(blank=True, related_name='events', through='dominion.OrgEventParticipation',
                                         to='dominion.Organization'),
        ),
        # convert PraiseOrCondemn.target to the assetowner of previous targets
        migrations.AddField(
            model_name='praiseorcondemn', name='temporary',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='so_temporary',
                                    to='dominion.AssetOwner', null=True)
        ),
        migrations.RunPython(store_previous_target_asset_owners_in_temp_field),
        migrations.AlterField(
            model_name='praiseorcondemn',
            name='target',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='praises_received',
                                    to='dominion.AssetOwner'),
        ),
        migrations.RunPython(switch_asset_owners_into_new_field),
        migrations.RemoveField(
            model_name='praiseorcondemn',
            name='temporary'
        ),
        # convert all participants of previous events into new format
        migrations.RunPython(populate_participants),
        migrations.RemoveField(
            model_name='rpevent',
            name='gms',
        ),
        migrations.RemoveField(
            model_name='rpevent',
            name='hosts',
        ),
        migrations.RemoveField(
            model_name='rpevent',
            name='participants',
        ),
    ]
