Arx is a game based on Evennia. It has the following requirements:
'pip install unidecode' for use during the guest process
'pip install cloudinary' for the CDN backend
for helpdesk, pip install the following: 'django-markdown-deux,
humanize, django-bootstrap-form'

It requires the following added to settings.py:
#-----------------------------------------------------------------
CHANNEL_COMMAND_CLASS = "commands.commands.channels.ArxChannelCommand"

BASE_ROOM_TYPECLASS = "typeclasses.rooms.ArxRoom"

TEMPLATES[0]['OPTIONS']['context_processors'] += [
    'web.character.context_processors.consts']

INSTALLED_APPS += ('world.dominion',
                   'world.msgs',
                   'web.character',
                   'web.news',
                   'web.helpdesk',
                   'web.help_topics',
                   'cloudinary',
                   'django.contrib.humanize',
                   'markdown_deux',
                   'bootstrapform')

COLOR_ANSI_EXTRA_MAP = color_markups.CURLY_COLOR_ANSI_EXTRA_MAP + color_markups.MUX_COLOR_ANSI_EXTRA_MAP
COLOR_XTERM256_EXTRA_FG = color_markups.CURLY_COLOR_XTERM256_EXTRA_FG + color_markups.MUX_COLOR_XTERM256_EXTRA_FG
COLOR_XTERM256_EXTRA_BG = color_markups.CURLY_COLOR_XTERM256_EXTRA_BG + color_markups.MUX_COLOR_XTERM256_EXTRA_BG
COLOR_XTERM256_EXTRA_GFG = color_markups.CURLY_COLOR_XTERM256_EXTRA_GFG + color_markups.MUX_COLOR_XTERM256_EXTRA_GFG
COLOR_XTERM256_EXTRA_GBG = color_markups.CURLY_COLOR_XTERM256_EXTRA_GBG + color_markups.MUX_COLOR_XTERM256_EXTRA_GBG
COLOR_ANSI_BRIGHT_BG_EXTRA_MAP = color_markups.CURLY_COLOR_ANSI_XTERM256_BRIGHT_BG_EXTRA_MAP + color_markups.MUX_COLOR_ANSI_XTERM256_BRIGHT_BG_EXTRA_MAP
PERMISSION_HIERARCHY = ["Guest",
                        "Player",
                        "Helper",
                        "Builder",
                        "Wizard",
                        "Admin",
                        "Immortal",
                        "Developer",
                        ]


HELPDESK_CREATE_TICKET_HIDE_ASSIGNED_TO = True


REQUEST_QUEUE_ID = 1

BUG_QUEUE_ID = 2
#----------------------------------------------------------------

Evennia resources:

From here on you might want to look at one of the beginner tutorials:
http://github.com/evennia/evennia/wiki/Tutorials.

Evennia's documentation is here: 
https://github.com/evennia/evennia/wiki.

Enjoy!
