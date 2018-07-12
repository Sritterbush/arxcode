"""
Commands for petitions app
"""
from server.utils.arx_utils import ArxCommand
from server.utils.exceptions import PayError
from world.petitions.models import BrokeredSale


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

    class BrokerError(Exception):
        """Errors when using the broker"""
        pass

    def func(self):
        """Executes broker command"""
        try:
            if not self.args or "search" in self.switches:
                return self.broker_display()
            if not self.switches:
                return self.display_sale_detail()
            if "buy" in self.switches:
                return self.make_purchase()
            if "sell" in self.switches:
                return self.make_sale_offer()
            raise self.BrokerError("Invalid switch.")
        except (self.BrokerError, PayError) as err:
            self.msg(err)

    def broker_display(self):
        """Displays items for sale on the broker"""
        from server.utils.prettytable import PrettyTable
        qs = BrokeredSale.objects.filter(amount__gte=1)
        if "search" in self.switches and self.args:
            from django.db.models import Q
            args = self.args.lower()
            if args in ("ap", "action points", "action_points"):
                query = Q(sale_type=BrokeredSale.ACTION_POINTS)
            elif "economic" in args:
                query = Q(sale_type=BrokeredSale.ECONOMIC)
            elif "social" in args:
                query = Q(sale_type=BrokeredSale.SOCIAL)
            elif "military" in args:
                query = Q(sale_type=BrokeredSale.MILITARY)
            else:
                query = Q(crafting_material_type__icontains=args) | Q(owner__player__username__iexact=args)
            qs = qs.filter(query)

        table = PrettyTable(["ID", "Seller", "Type", "Price", "Amount"])
        for deal in qs:
            table.add_row([deal.id, str(deal.owner), str(deal.material_name), deal.price, deal.amount])
        self.msg(str(table))

    def display_sale_detail(self):
        """Displays information about a sale"""
        sale = self.find_brokered_sale_by_id(self.lhs)
        self.msg(sale.display(self.caller))

    def make_purchase(self):
        """Buys some amount from a sale"""
        sale = self.find_brokered_sale_by_id(self.lhs)
        amount = self.get_amount(self.rhs)
        dompc = self.caller.player_ob.Dominion
        cost = sale.make_purchase(dompc, amount)
        self.msg("You have bought %s %s from %s for %s silver." % (amount, sale.material_name, sale.owner, cost))

    def get_amount(self, args):
        """Gets a positive number to use as a transaction, or raises a BrokerError"""
        try:
            amount = int(args)
            if amount <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise self.BrokerError("You must provide a positive number as the amount.")
        return amount

    def make_sale_offer(self):
        if len(self.rhslist) != 2:
            raise self.BrokerError("You must provide a type and an amount to sell.")
        amount = self.get_amount(self.rhslist[1])
        pass

    def find_brokered_sale_by_id(self, args):
        """Tries to find a brokered sale with ID that matches args or raises BrokerError"""
        try:
            return BrokeredSale.objects.get(id=args)
        except (BrokeredSale.DoesNotExist, ValueError, TypeError):
            raise self.BrokerError("Could not find a sale on the broker by the ID %s." % args)
