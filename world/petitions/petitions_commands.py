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
        broker/sell <type>=<amount>,<price>
        broker/cancel <ID #>

    Allows you to automatically buy or sell crafting materials or
    more abstract things such as influence with npcs (resources)
    or time (action points). To sell or buy action points, specify
    'action points' or 'ap' as the type. To sell or buy resources,
    specify the type of resource (economic, social, or military).
    It costs three times as much action points as the amount you
    put on the broker. All prices are per-unit.

    When searching, you can specify the name of a seller, a type
    of crafting material or resource (umbra, economic, etc), ap,
    or categories such as 'resources' or 'materials'.
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
            if "cancel" in self.switches:
                return self.cancel_sale()
            raise self.BrokerError("Invalid switch.")
        except (self.BrokerError, PayError) as err:
            self.msg(err)

    def get_sale_type(self):
        """Gets the constant based on types of args players might enter"""
        args = self.lhs.lower()
        if args in ("ap", "action points", "action_points"):
            return BrokeredSale.ACTION_POINTS
        elif "economic" in args:
            return BrokeredSale.ECONOMIC
        elif "social" in args:
            return BrokeredSale.SOCIAL
        elif "military" in args:
            return BrokeredSale.MILITARY
        else:
            return BrokeredSale.CRAFTING_MATERIALS

    def broker_display(self):
        """Displays items for sale on the broker"""
        from server.utils.prettytable import PrettyTable
        qs = BrokeredSale.objects.filter(amount__gte=1)
        if "search" in self.switches and self.args:
            from django.db.models import Q
            sale_type = self.get_sale_type()
            if sale_type in (BrokeredSale.ACTION_POINTS, BrokeredSale.ECONOMIC,
                             BrokeredSale.SOCIAL, BrokeredSale.MILITARY):
                query = Q(sale_type=sale_type)
            else:
                if set(self.args.lower().split()) & {"materials", "mats", "crafting"}:
                    query = Q(sale_type=BrokeredSale.CRAFTING_MATERIALS)
                elif "resource" in self.args.lower():
                    query = Q(sale_type__in=(BrokeredSale.ECONOMIC, BrokeredSale.SOCIAL, BrokeredSale.MILITARY))
                else:
                    query = (Q(crafting_material_type__name__icontains=self.args) |
                             Q(owner__player__username__iexact=self.args))
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
        if sale.owner == dompc:
            raise self.BrokerError("You can't buy from yourself. Cancel it instead.")
        cost = sale.make_purchase(dompc, amount)
        self.msg("You have bought %s %s from %s for %s silver." % (amount, sale.material_name, sale.owner, cost))

    def get_amount(self, args, noun="amount"):
        """Gets a positive number to use for a transaction, or raises a BrokerError"""
        try:
            amount = int(args)
            if amount <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise self.BrokerError("You must provide a positive number as the %s." % noun)
        return amount

    def make_sale_offer(self):
        """Create a new sale"""
        if len(self.rhslist) != 2:
            raise self.BrokerError("You must ask for both an amount and a price.")
        amount = self.get_amount(self.rhslist[0])
        price = self.get_amount(self.rhslist[1], "price")
        sale_type = self.get_sale_type()
        material_type = None
        resource_types = dict(BrokeredSale.RESOURCE_TYPES)
        if sale_type == BrokeredSale.ACTION_POINTS:
            if amount % 3:
                raise self.BrokerError("Action Points must be a factor of 3, since it's divided by 3 when put on sale.")
            if not self.caller.player_ob.pay_action_points(amount):
                raise self.BrokerError("You do not have enough action points to put on sale.")
            amount /= 3
        elif sale_type in resource_types:
            resource = resource_types[sale_type]
            if not self.caller.player_ob.pay_resources(resource, amount):
                raise self.BrokerError("You do not have enough %s resources to put on sale." % resource)
        else:
            from world.dominion.models import CraftingMaterialType
            try:
                material_type = CraftingMaterialType.objects.get(name__iexact=self.lhs)
            except CraftingMaterialType.DoesNotExist:
                raise self.BrokerError("Could not find a material by the name '%s'." % self.lhs)
            if "nosell" in (material_type.acquisition_modifiers or ""):
                raise self.BrokerError("You can't put contraband on the broker! Seriously, how are you still alive?")
            if not self.caller.player_ob.pay_materials(material_type, amount):
                raise self.BrokerError("You don't have enough %s to put on sale." % material_type)
        dompc = self.caller.player_ob.Dominion
        sale, created = dompc.brokered_sales.get_or_create(price=price, sale_type=sale_type,
                                                           crafting_material_type=material_type)
        sale.amount += amount
        sale.save()
        if created:
            self.msg("Created a new sale of %s %s for %s silver." % (amount, sale.material_name, price))
        else:
            self.msg("Added %s to the existing sale of %s for %s silver." % (amount, sale.material_name, price))

    def find_brokered_sale_by_id(self, args):
        """Tries to find a brokered sale with ID that matches args or raises BrokerError"""
        try:
            return BrokeredSale.objects.get(id=args)
        except (BrokeredSale.DoesNotExist, ValueError, TypeError):
            raise self.BrokerError("Could not find a sale on the broker by the ID %s." % args)

    def cancel_sale(self):
        sale = self.find_brokered_sale_by_id(self.lhs)
        if sale.owner != self.caller.player_ob.Dominion:
            raise self.BrokerError("You can only cancel your own sales.")
        sale.cancel()
        self.msg("You have cancelled the sale.")
