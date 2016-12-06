from server.utils.arx_utils import sub_old_ansi


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
        """
        :type self: evennia.objects.models.ObjectDB
        :return:
        """
        return self.db.desc or self.db.raw_desc or self.db.general_desc

    def __desc_set(self, val):
        """
        :type self: ObjectDB
        """
        # desc may be changed dynamically
        self.db.raw_desc = val
        self.db.desc = val
        # general desc is our fallback
        self.db.general_desc = val
    desc = property(__desc_get, __desc_set)

    def __temp_desc_get(self):
        """
        :type self: ObjectDB
        """
        return self.db.desc or self.db.raw_desc or self.db.general_desc

    def __temp_desc_set(self, val):
        """
        :type self: ObjectDB
        """
        # Make sure we're not using db.desc as our permanent desc before wiping it
        if not self.db.raw_desc:
            self.db.raw_desc = self.db.desc
        if not self.db.general_desc:
            self.db.desc = self.db.desc
        self.db.desc = val

    def __temp_desc_del(self):
        """
        :type self: ObjectDB
        """
        # Make sure we're not using db.desc as our permanent desc before wiping it
        if not self.db.raw_desc:
            self.db.raw_desc = self.db.desc
        if not self.db.general_desc:
            self.db.general_desc = self.db.desc
        self.db.desc = ""
    temp_desc = property(__temp_desc_get, __temp_desc_set, __temp_desc_del)

    def __perm_desc_get(self):
        """
        :type self: ObjectDB
        :return:
        """
        return self.db.raw_desc or self.db.general_desc or self.db.desc

    def __perm_desc_set(self, val):
        """
        :type self: ObjectDB
        """
        self.db.general_desc = val
        self.db.raw_desc = val
    perm_desc = property(__perm_desc_get, __perm_desc_set)

    def __get_volume(self):
        """
        :type self: ObjectDB
        """
        total = 0
        for obj in self.contents:
            if obj.db.worn_by != self and obj.db.sheathed_by != self:
                vol = obj.db.volume or 1
                total += vol
        return total
    volume = property(__get_volume)

    @property
    def health_status(self):
        """
        :type self: ObjectDB
        """
        return self.db.health_status or "nonliving"

    @health_status.setter
    def health_status(self, value):
        """
        :type self: ObjectDB
        """
        self.db.health_status = value

    @property
    def dead(self):
        return self.health_status == "dead"

    @property
    def alive(self):
        return self.health_status == "alive"


class NameMixins(object):

    @property
    def is_disguised(self):
        return bool(self.fakename)

    @property
    def fakename(self):
        """
        :type self: ObjectDB
        """
        return self.db.false_name

    @fakename.setter
    def fakename(self, val):
        """
        :type self: ObjectDB
        :param val: str
        """
        old = self.db.false_name
        self.db.false_name = val
        if old:
            self.aliases.remove(old)
        self.aliases.add(val)

    @fakename.deleter
    def fakename(self):
        """
        :type self: ObjectDB
        """
        old = self.db.false_name
        if old:
            self.aliases.remove(old)
        self.attributes.remove("false_name")

    def __name_get(self):
        """
        :type self: ObjectDB
        """
        return self.fakename or self.db.colored_name or self.key

    def __name_set(self, val):
        """
        :type self: ObjectDB
        """
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

        :type self: evennia.objects.models.ObjectDB
        :param pobject: ObjectDB
        :param detailed: bool
        :param show_ids: bool
        :param strip_ansi: bool
        :param show_places: bool
        """
        def get_key(ob):
            if show_ids:
                object_key = "%s {w(ID: %s){n" % (ob.name, ob.id)
            else:
                object_key = ob.name
            if strip_ansi:
                try:
                    from evennia.utils.ansi import parse_ansi
                    object_key = parse_ansi(object_key, strip_ansi=True)
                except (AttributeError, TypeError, ValueError):
                    pass
            return object_key
        string = ""
        # get and identify all objects
        visible = (con for con in self.contents if con != pobject and con.access(pobject, "view"))
        exits, users, things, worn, sheathed, wielded, places = [], [], [], [], [], [], []
        currency = self.return_currency()
        from typeclasses.places.places import Place
        qs = list(Place.objects.filter(db_location=self))
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
                # we might have either a title or a fake name
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
            string += "\n" + "{wWielding:{n " + ", ".join(wielded)
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
        :type self: ObjectDB
        :param amount: int
        :param receiver: ObjectDB
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
    
    def return_currency(self):
        """
        :type self: ObjectDB
        """
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
        :type self: ObjectDB
        :param pobject: ObjectDB
        :param detailed: bool
        :param format_desc: bool
        :param show_contents: bool
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
            except (AttributeError, ValueError, TypeError):
                pass
        if desc and not self.db.recipe and not self.db.do_not_format_desc and "player_made_room" not in self.tags.all():
            if format_desc:

                string += "\n\n%s{n\n" % desc
            else:
                string += "\n%s{n" % desc
        else:  # for crafted objects, respect formatting
            string += "\n%s{n" % desc
        if contents and show_contents:
            string += contents
        string += self.return_crafting_desc()
        return string

    def return_crafting_desc(self):
        """
        :type self: ObjectDB
        """
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
        """
        :type self: ObjectDB
        :param text: str
        :param from_obj: ObjectDB
        :param session: Session
        :param options: dict
        :param kwargs: dict
        """
        options = options or {}
        options.update(kwargs.get('options', {}))
        try:
            text = str(text)
        except (TypeError, UnicodeDecodeError, ValueError):
            pass
        text = sub_old_ansi(text)
        if options.get('is_pose', False):
            if self.db.posebreak:
                text = "\n" + text
            quote_color = self.db.pose_quote_color
            # colorize people's quotes with the given text
            if quote_color:
                import re

        if options.get('box', False):
            boxchars = '\n{w' + '*' * 70 + '{n\n'
            text = boxchars + text + boxchars
        if options.get('roll', False):
            if self.attributes.has("dice_string"):
                text = "{w<" + self.db.dice_string + "> {n" + text
        if from_obj and isinstance(from_obj, dict):
            print "DEBUG in MsgMixins: from_obj is %s" % from_obj
        try:
            if self.db.char_ob:
                msg_sep = self.tags.get("newline_on_messages")
            else:
                msg_sep = self.db.player_ob.tags.get("newline_on_messages")
        except AttributeError:
            msg_sep = None
        try:
            if msg_sep:
                text += "\n"
        except (TypeError, ValueError):
            pass
        super(MsgMixins, self).msg(text, from_obj, session, options, **kwargs)


class LockMixins(object):
    def lock(self, caller=None):
        """
        :type self: ObjectDB
        :param caller: ObjectDB
        """
        self.locks.add("traverse: perm(builders)")
        if self.db.locked:
            if caller:
                caller.msg("%s is already locked." % self)
            return
        if caller and not self.access(caller, 'usekey'):
            caller.msg("You do not have a key to %s." % self)
            return
        self.db.locked = True      
        msg = "%s is now locked." % self.key
        if caller:
            caller.msg(msg)
        self.location.msg_contents(msg, exclude=caller)
        # set the locked attribute of the destination of this exit, if we have one
        if self.destination and hasattr(self.destination, 'entrances') and self.destination.db.locked is False:
            entrances = [ob for ob in self.destination.entrances if ob.db.locked is False]
            if not entrances:
                self.destination.db.locked = True

    def unlock(self, caller=None):
        """
        :type self: ObjectDB:
        :param caller: ObjectDB
        :return:
        """
        self.locks.add("traverse: all()")
        if not self.db.locked:
            if caller:
                caller.msg("%s is already unlocked." % self)
            return
        if caller and not self.access(caller, 'usekey'):
            caller.msg("You do not have a key to %s." % self)
            return
        self.db.locked = False  
        msg = "%s is now unlocked." % self.key
        if caller:
            caller.msg(msg)
        self.location.msg_contents(msg, exclude=caller)
        if self.destination:
            self.destination.db.locked = False

    def return_appearance(self, pobject, detailed=False, format_desc=False,
                          show_contents=True):
        """
        :type self: AppearanceMixins, Container
        :param pobject: ObjectDB
        :param detailed: bool
        :param format_desc: bool
        :param show_contents: bool
        :return: str
        """
        currently_open = not self.db.locked
        show_contents = currently_open and show_contents
        base = super(LockMixins, self).return_appearance(pobject, detailed=detailed,
                                                         format_desc=format_desc, show_contents=show_contents)
        return base + "\nIt is currently %s." % ("locked" if self.db.locked else "unlocked")
