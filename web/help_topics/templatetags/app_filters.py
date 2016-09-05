from django import template
from django.template.defaultfilters import stringfilter
from django.utils.safestring import mark_safe
from evennia.utils.ansi import parse_ansi

register = template.Library()

@register.filter
def mush_to_html(value):
    if not value:
        return value
    value = value.replace('<', '(')
    value = value.replace('>', ')')
    value = value.replace('%r', '<br>')
    value = value.replace('\n', '<br>')
    value = value.replace('%b', ' ')
    value = value.replace('%t', '&nbsp&nbsp&nbsp&nbsp')
    #value = value.replace('{w', '<strong>')
    #value = value.replace('{n', '</strong>')
    value = parse_ansi(value, strip_ansi=True)
    return mark_safe(value)
