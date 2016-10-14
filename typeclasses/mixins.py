from evennia.utils.utils import fill
from server.utils.utils import sub_old_ansi



class DescMixins(object):
    """
    Handles descriptions for objects, which is controlled by three
    Evennia Attributes: desc, raw_desc, and general_desc. desc is
    the current description that is used/seen when looking at an
    object. raw_desc is a permanent desc that might be elaborated
    upon with other things, such as additional strings from other
    methods or properties. general_desc is a fallback that can be
    used if raw_desc is unavailable or unused.

    These are accessed by three properties: desc, temp_desc, and
    perm_desc. desc returns the temporary desc first if it exists,
    then the raw_desc, then the fallback general_desc, the the desc
    setter will set all three of these to the same value, intended
    to be a universal change. temp_desc will return the same value
    as desc, but its setter only modifies the temporary desc, and
    it has a deleter that sets the temporary desc to an empty string.
    perm_desc returns the raw_desc first or its fallback, only returning
    the temporary desc if neither exist. Its setter sets the general_desc
    and raw_desc, but not the temporary desc.

    So for a temporary disguise, use .temp_desc. For a permanent change
    that won't override any current disguise, use .perm_desc. For a change
    that will change everything right now, disguise or not, use .desc.
    """
    def __desc_get(self):
        return self.db.desc or self.db.raw_desc or self.db.general_desc
    def __desc_set(self, val):
        # desc may be changed dynamically
        self.db.raw_desc = val
        self.db.desc = val
        # general desc is our fallback
        self.db.general_desc = val
    desc = property(__desc_get, __desc_set)
    def __temp_desc_get(self):
        return self.db.desc or self.db.raw_desc or self.db.general_desc
    def __temp_desc_set(self, val):
        self.db.desc = val
    def __temp_desc_del(self):
        self.db.desc = ""
    temp_desc = property(__temp_desc_get, __temp_desc_set, __temp_desc_del)
    def __perm_desc_get(self):
        return self.db.raw_desc or self.db.general_desc or self.db.desc
    def __perm_desc_set(self, val):
        self.db.general_desc = val
        self.db.raw_desc = val
    perm_desc = property(__perm_desc_get, __perm_desc_set)
    def __get_volume(self):
        total = 0
        for obj in self.contents:
            if obj.db.worn_by != self and obj.db.sheathed_by != self:
                vol = obj.db.volume or 1
                total += vol
        return total
    volume = property(__get_volume)

class NameMixins(object):
    def __name_get(self):
        return self.db.colored_name or self.key
    def __name_set(self, val):
        from evennia.utils.ansi import parse_ansi
        # convert color codes
        val = sub_old_ansi(val)
        self.db.colored_name = val
        self.key = parse_ansi(val, strip_ansi=True)
        self.save()
    name = property(__name_get, __name_set)
    
    def __str__(self):
        return self.name

class AppearanceMixins(object):
    
    def return_contents(self, pobject, detailed=True, show_ids=False,
                        strip_ansi=False, show_places=True):
        """
        Returns contents of the object, used in formatting our description,
        as well as when in 'brief mode' and skipping a description, but
        still seeing contents.
        """
        def get_key(ob):
            if show_ids:
                key = "%s {w(ID: %s){n" % (ob.name, ob.id)
            else:
                key = ob.name
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
        exits, users, things, worn, sheathed, wielded, places = [], [], [], [], [], [], []
        currency = self.return_currency(pobject)
        try:
            from typeclasses.places.places import Place
            qs = Place.objects.filter(db_location=self)
        except Exception:
            qs = []
        for con in visible:
            key = get_key(con)
            if con in qs and show_places:
                places.append(key)
                continue
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
            if show_places and places:
                string += "\n{wPlaces:{n " + ", ".join(places)
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
                string += "\n\n%s{n\n" % desc #fill(desc, indent=indent)
            else:
                string += "\n%s{n" % desc #fill(desc)
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

class ObjectMixins(DescMixins, AppearanceMixins):

    @property
    def is_room(self):
        return False
    @property
    def is_exit(self):
        return False
    @property
    def is_character(self):
        return False

class MsgMixins(object):
    def msg(self, text=None, from_obj=None, session=None, options=None, **kwargs):
        options = options or {}
        options.update(kwargs.get('options', {}))
        try:
            text = str(text)
        except Exception:
            pass
        text = sub_old_ansi(text)
        if options.get('is_pose', False):
            if self.db.posebreak:
                text = "\n" + text
        if options.get('box', False):
            boxchars = '\n{w' + '*' * 60 + '{n\n'
            text = boxchars + text + boxchars
        if options.get('roll', False):
            if self.attributes.has("dice_string"):
                text = "{w<" + self.db.dice_string + "> {n" + text
        super(MsgMixins, self).msg(text, from_obj, session, options, **kwargs)
