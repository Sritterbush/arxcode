from evennia.utils.utils import fill

class ObjectMixins(object):
    def __desc_get(self):
        return self.db.desc
    def __desc_set(self, val):
        self.db.desc = val
    desc = property(__desc_get, __desc_set)
    def return_contents(self, pobject, detailed=True, show_ids=False, strip_ansi=False):
        """
        Returns contents of the object, used in formatting our description,
        as well as when in 'brief mode' and skipping a description, but
        still seeing contents.
        """
        def get_key(ob):
            if show_ids:
                key = "%s {w(ID: %s){n" % (ob.key, ob.id)
            else:
                key = ob.key
            if strip_ansi:
                try:
                    from evennia.utils.ansi import parse_ansi
                    key = parse_ansi(key, strip_ansi=True)
                except Exception:
                    pass
            return key
        string = ""
        # get and identify all objects
        visible = (con for con in self.contents if con != pobject and
                                                    con.access(pobject, "view"))
        exits, users, things, worn, sheathed, wielded = [], [], [], [], [], []
        currency = self.return_currency(pobject)
        for con in visible:
            key = get_key(con)
##            if show_ids:
##                key = "%s {w(ID: %s){n" % (con.key, con.id)
##            else:
##                key = con.key
            if con.destination:
                exits.append(key)
            # Only display worn items in inventory to other characters
            elif con.db.worn_by and con.db.worn_by == self:
                worn.append(con)
            elif con.db.wielded_by == self:
                if not con.db.stealth:
                    wielded.append(key)
                elif hasattr(pobject, 'sensing_check') and pobject.sensing_check(con, diff=con.db.sense_difficulty) > 0:
                    key += "{w(hidden){n"
                    wielded.append(key)
            elif con.db.sheathed_by == self:
                sheathed.append(key)
            elif con.has_player:
                #we might have either a title or a fake name
                lname = con.name
                if con.key in lname and not con.db.false_name:
                    lname = lname.replace(key, "{c%s{n" % key)
                    users.append(lname)
                else:
                    users.append("{c%s{n" % lname)
            else:
                if not self.db.places:
                    things.append(con)
                elif self.db.places and con not in self.db.places:
                    things.append(con)
        if worn:
            worn = sorted(worn, key=lambda x: x.db.worn_time)
            string += "\n" + "{wWorn items of note:{n " + ", ".join(get_key(ob) for ob in worn)
        if sheathed:
            string += "\n" + "{wWorn/Sheathed weapons:{n " + ", ".join(sheathed)
        if wielded:
            string += "\n"  + "{wWielding:{n " + ", ".join(wielded)
        if detailed:
            if exits:
                string += "\n{wExits:{n " + ", ".join(exits)
            if users or things:
                if things:
                    things = sorted(things, key=lambda x: x.db.put_time)
                string += "\n{wYou see:{n " + ", ".join(users + [get_key(ob) for ob in things])
            if currency:
                string += "\n{wMoney:{n %s" % currency
        return string
    
    def pay_money(self, amount, receiver=None):
        """
        A method to pay money from this object, possibly to a receiver.
        All checks should be done before this, and messages also sent
        outside. This just transfers the money itself.
        """
        currency = self.db.currency or 0.0
        currency = round(currency, 2)
        amount = round(amount, 2)
        if amount > currency:
            raise Exception("pay_money called without checking sufficient funds in character. Not enough.")
        self.db.currency = currency - amount
        if receiver:
            if not receiver.db.currency:
                receiver.db.currency = 0.0
            receiver.db.currency += amount
        return True
    
    def return_currency(self, pobject):
        currency = self.db.currency
        if not currency:
            return None
        string = "coins worth a total of %.2f silver pieces" % currency
        return string

    def return_appearance(self, pobject, detailed=False, format_desc=False,
                          show_contents=True):
        """
        This is a convenient hook for a 'look'
        command to call.
        """
        if not pobject:
            return
        strip_ansi = pobject.db.stripansinames
        # always show contents if a builder+
        show_contents = show_contents or pobject.check_permstring("builders")
        contents = self.return_contents(pobject, strip_ansi=strip_ansi)
        # get description, build string
        string = "{c%s{n" % self.name
        # if altered_desc is true, we use the alternate desc set by an attribute.
        # usually this is some dynamic description set at runtime, such as based
        # on an illusion, wearing a mask, change of seasons, etc.
        if self.db.altered_desc:
            desc = self.db.desc
        else:
            desc = self.desc
        if strip_ansi:
            try:
                from evennia.utils.ansi import parse_ansi
                desc = parse_ansi(desc, strip_ansi=True)
            except Exception:
                pass
        if desc and not self.db.recipe and not self.db.do_not_format_desc and not "player_made_room" in self.tags.all():
            if format_desc:
                indent = 0
                if len(desc) > 78:
                    indent = 4
                string += "\n\n%s{n\n" % fill(desc, initial_indent=indent)
            else:
                string += "\n%s{n" % fill(desc)
        else: # for crafted objects, respect formatting
            string += "\n%s{n" % desc
        if contents and show_contents:
            string += contents
        string += self.return_crafting_desc(pobject)   
        return string

    def return_crafting_desc(self, looker=None):
        string = ""
        adorns = self.db.adorns or {}
        # adorns are a dict of the ID of the crafting material type to amount
        if adorns:
            from world.dominion.models import CraftingMaterialType
            adorn_strs = []
            for adorn_id in adorns:
                amt = adorns[adorn_id]
                try:
                    mat = CraftingMaterialType.objects.get(id=adorn_id)
                except CraftingMaterialType.DoesNotExist:
                    continue
                adorn_strs.append("%s %s" % (amt, mat.name))
            string += "\nAdornments: %s" % ", ".join(adorn_strs)
        # recipe is an integer matching the CraftingRecipe ID
        if self.db.recipe:
            from world.dominion.models import CraftingRecipe
            try:
                recipe = CraftingRecipe.objects.get(id=self.db.recipe)
                string += "\nIt is a %s." % recipe.name
            except CraftingRecipe.DoesNotExist:
                pass
        # quality_level is an integer, we'll get a name from crafter file's dict
        if self.db.quality_level:
            from commands.commands.crafting import QUALITY_LEVELS
            qual = self.db.quality_level
            qual = QUALITY_LEVELS.get(qual, "average")
            string += "\nIts level of craftsmanship is %s." % qual
        # signed_by is a crafter's character object
        signed = self.db.signed_by
        if signed:
            string += "\n%s" % (signed.db.crafter_signature or "")
        return string

class MsgMixins(object):
    def msg(self, text=None, from_obj=None, session=None, options=None, **kwargs):
        text = text.replace("%r", "|/").replace("%t", "|-")
        super(MsgMixins, self).msg(text, from_obj, session, options, **kwargs)
