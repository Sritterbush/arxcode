# -*- coding: utf-8 -*-
"""Admin models for Fashion"""
from __future__ import unicode_literals

from django.contrib import admin

from .models import FashionSnapshot


class SnapshotAdmin(admin.ModelAdmin):
    """Snapshot admin class"""
    list_display = ('id', 'fashion_model', 'fashion_item_raw_name', 'org', 'fame')
    list_select_related = True
    raw_id_fields = ('fashion_item', 'fashion_model', 'org')

    @staticmethod
    def fashion_item_raw_name(obj):
        """Strips ansi from string display"""
        return obj.fashion_item and obj.fashion_item.key

admin.site.register(FashionSnapshot, SnapshotAdmin)
