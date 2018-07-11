"""
Commands for petitions app
"""
from server.utils.arx_utils import ArxCommand


class CmdPetition(ArxCommand):
    """
    Creates a petition to an org or the market as a whole

    Usage:
    -Viewing/Signups:
        petition [<# to view>]
        petition/search <keyword>
        petition/signup <#>
    -Creation/Deletion:
        petition/create [<topic>][=<description>]
        petition/topic <topic>
        petition/desc <description>
        petition/ooc <ooc notes>
        petition/org <organization>
        petition/submit
        petition/cancel <#>

    Create a petition that is either submitted to an organization or
    posted in the market for signups.
    """