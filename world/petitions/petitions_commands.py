"""
Commands for petitions app
"""
from server.utils.arx_utils import ArxCommand
from world.petitions.models import BrokeredDeal


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
    key = "petition"
    help_category = "Market"

    def func(self):
        """Executes petition command"""
        pass


class CmdBroker(ArxCommand):
    """
    Buy or sell AP/Resources in the market

    Usage:
        broker/search <type>
        broker/buy <ID #>=<amount>
        broker/sell <buyer>=<type>,<amount>
        broker/cancel <ID #>

    Allows you to automatically buy or sell crafting materials or
    more abstract things such as influence with npcs (resources)
    or time (action points). To sell or buy action points, specify
    'action points' or 'ap' as the type. To sell or buy resources,
    specify the type of resource (economic, social, or military).
    """
    key = "broker"
    help_category = "Market"

    def func(self):
        """Executes broker command"""
        if not self.args or "search" in self.switches:
            return self.broker_display()
        if not self.switches:
            return self.display_deal_detail()
        if "buy" in self.switches:
            return self.make_purchase()
        if "sell" in self.switches:
            return self.make_sale_offer()

    def broker_display(self):
        """Displays items for sale on the broker"""
        from server.utils.prettytable import PrettyTable
        qs = BrokeredDeal.objects.filter(amount__gte=1)
        if "search" in self.switches and self.args:
            from django.db.models import Q
            args = self.args.lower()
            if args in ("ap", "action points", "action_points"):
                query = Q(offering_type=BrokeredDeal.ACTION_POINTS)
            elif "economic" in args:
                query = Q(offering_type=BrokeredDeal.ECONOMIC)
            elif "social" in args:
                query = Q(offering_type=BrokeredDeal.SOCIAL)
            elif "military" in args:
                query = Q(offering_type=BrokeredDeal.MILITARY)
            else:
                query = Q(crafting_material_type__icontains=args) | Q(owner__player__username__iexact=args)
            qs = qs.filter(query)

        table = PrettyTable(["ID", "Seller", "Type", "Price", "Amount"])
        for deal in qs:
            table.add_row([deal.id, deal.owner, deal.material_name, deal.price, deal.amount])
        self.msg(str(table))

    def display_deal_detail(self):
        pass

    def make_purchase(self):
        pass

    def make_sale_offer(self):
        pass