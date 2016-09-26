from django.db import models
from django.conf import settings
from cloudinary.models import CloudinaryField
from evennia.objects.models import ObjectDB
from evennia.locks.lockhandler import LockHandler
from django.db.models import Q, F
from .managers import ArxRosterManager
from datetime import datetime

"""
This is the main model in the project. It holds a reference to cloudinary-stored
image and contains some metadata about the image.
"""
class Photo(models.Model):
    ## Misc Django Fields
    create_time = models.DateTimeField(auto_now_add=True)
    title = models.CharField("Name or description of the picture (optional)", max_length=200, blank=True)
    owner = models.ForeignKey("objects.ObjectDB", blank=True, null=True, verbose_name='owner',
                                  help_text='a Character owner of this image, if any.')
    alt_text = models.CharField("Optional 'alt' text when mousing over your image", max_length=200, blank=True)

    ## Points to a Cloudinary image
    image = CloudinaryField('image')

    """ Informative name for mode """
    def __unicode__(self):
        try:
            public_id = self.image.public_id
        except AttributeError:
            public_id = ''
        return "Photo <%s:%s>" % (self.title, public_id)


class Roster(models.Model):
    """
    A model for storing lists of entries of characters. Each RosterEntry has
    information on the Player and Character objects of that entry, information
    on player emails of previous players, GM notes, etc. The Roster itself just
    has locks for determining who can view the contents of a roster.
    """
    name = models.CharField(blank=True, null=True, max_length=255)
    lock_storage = models.TextField('locks', blank=True, help_text='defined in setup_utils')
    objects = ArxRosterManager()
    def __init__(self, *args, **kwargs):
        super(Roster, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)

    def access(self, accessing_obj, access_type='view', default=True):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)

    def __unicode__(self):
        return self.name or 'Unnamed Roster'


class RosterEntry(models.Model):
    roster = models.ForeignKey('Roster', related_name='entries',
                               on_delete=models.SET_NULL, blank=True, null=True)
    player = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='roster', blank=True, null=True)
    character = models.OneToOneField('objects.ObjectDB', related_name='roster', blank=True, null=True)
    current_account = models.ForeignKey('PlayerAccount', related_name='characters',
                                        on_delete=models.SET_NULL, blank=True, null=True)   
    previous_accounts = models.ManyToManyField('PlayerAccount', through='AccountHistory', blank=True)
    gm_notes = models.TextField(blank=True)
    # different variations of reasons not to display us
    inactive = models.BooleanField(default=False, null=False)
    frozen = models.BooleanField(default=False, null=False)
    # profile picture for sheet and also thumbnail for list
    profile_picture = models.ForeignKey('Photo', blank=True, null=True, on_delete=models.SET_NULL)
    # going to use for determining how our character page appears
    sheet_style = models.TextField(blank=True)
    lock_storage = models.TextField('locks', blank=True, help_text='defined in setup_utils')
    
    def __init__(self, *args, **kwargs):
        super(RosterEntry, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)

    class Meta:
        "Define Django meta options"
        verbose_name_plural = "Roster Entries"

    def __unicode__(self):
        if self.character:
            return self.character.key
        if self.player:
            return self.player.key
        return "Blank Entry"

    def access(self, accessing_obj, access_type='show_hidden', default=False):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)

    def fake_delete(self):
        try:
            delroster = Roster.objects.get(name__iexact="Deleted")
        except Roster.DoesNotExist:
            print "Could not find Deleted Roster!"
            return
        self.roster = delroster
        self.inactive = True
        self.frozen = True
        self.save()

    def undelete(self, rname="Active"):
        try:
            roster = Roster.objects.get(name__iexact=rname)
        except Roster.DoesNotExist:
            print "Could not find %s roster!" % rname
            return
        self.roster = roster
        self.inactive = False
        self.frozen = False
        self.save()

    def adjust_xp(self, val):
        try:
            if val < 0:
                return
            history = self.accounthistory_set.get(account=self.current_account)
            history.xp_earned += val
            history.save()
        except Exception:
            pass

    @property
    def finished_clues(self):
        return self.clues.filter(roll__gte=F('clue__rating'))

class Story(models.Model):
    current_chapter = models.OneToOneField('Chapter', related_name='current_chapter_story',
                                           on_delete=models.SET_NULL, blank=True, null=True)
    name = models.CharField(blank=True, null=True, max_length=255)
    synopsis = models.TextField(blank=True, null=True)
    season = models.PositiveSmallIntegerField(default=0, blank=0)
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        "Define Django meta options"
        verbose_name_plural = "Stories"

    def __str__(self):
        return self.name or "Story object"

class Chapter(models.Model):
    name = models.CharField(blank=True, null=True, max_length=255)
    synopsis = models.TextField(blank=True, null=True)
    story = models.ForeignKey('Story', blank=True, null=True,
                              on_delete=models.SET_NULL, related_name='previous_chapters')
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)
    def __str__(self):
        return self.name or "Chapter object"

class Episode(models.Model):
    name = models.CharField(blank=True, null=True, max_length=255)
    chapter = models.ForeignKey('Chapter', blank=True, null=True,
                                on_delete=models.SET_NULL, related_name='episodes')
    synopsis = models.TextField(blank=True, null=True)
    gm_notes = models.TextField(blank=True, null=True)
    date = models.DateTimeField(blank=True, null=True)
    def __str__(self):
        return self.name or "Episode object"

class StoryEmit(models.Model):
    # chapter only used if we're not specifically attached to some episode
    chapter = models.ForeignKey('Chapter', blank=True, null=True,
                                on_delete=models.SET_NULL, related_name='emits')
    episode = models.ForeignKey('Episode', blank=True, null=True,
                                on_delete=models.SET_NULL, related_name='emits')
    text = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    sender = models.ForeignKey('players.PlayerDB', blank=True, null=True,
                               on_delete=models.SET_NULL, related_name='emits')

class Milestone(models.Model):
    protagonist = models.ForeignKey('RosterEntry', related_name='milestones')
    name = models.CharField(blank=True, null=True, max_length=255)
    synopsis = models.TextField(blank=True, null=True)
    chapter = models.ForeignKey('Chapter', blank=True, null=True,
                                on_delete=models.SET_NULL, related_name='milestones')
    episode = models.ForeignKey('Episode', blank=True, null=True,
                                on_delete=models.SET_NULL, related_name='milestones')
    secret = models.BooleanField(default=False, null=False)
    image = models.ForeignKey('Photo', blank=True, null=True,
                              on_delete=models.SET_NULL, related_name='milestones')
    gm_notes = models.TextField(blank=True, null=True)
    participants = models.ManyToManyField('RosterEntry', through='Participant', blank=True)
    importance = models.PositiveSmallIntegerField(default=0, blank=0)

class Participant(models.Model):
    milestone = models.ForeignKey('Milestone', on_delete=models.CASCADE)
    character = models.ForeignKey('RosterEntry', on_delete=models.CASCADE)
    xp_earned = models.PositiveSmallIntegerField(default=0, blank=0)
    karma_earned = models.PositiveSmallIntegerField(default=0, blank=0)
    gm_notes = models.TextField(blank=True, null=True)

class Comment(models.Model):
    poster = models.ForeignKey('RosterEntry', related_name='comments')
    target = models.ForeignKey('RosterEntry', related_name='comments_upon', blank=True, null=True)
    text = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    gamedate = models.CharField(blank=True, null=True, max_length=80)
    reply_to = models.ForeignKey('self', blank=True, null=True)
    milestone = models.ForeignKey('Milestone', blank=True, null=True, related_name='comments')

class PlayerAccount(models.Model):
    email = models.EmailField(unique=True)
    karma = models.PositiveSmallIntegerField(default=0, blank=0)
    gm_notes = models.TextField(blank=True, null=True)

    def __unicode__(self):
        return str(self.email)
    
    @property
    def total_xp(self):
        qs = self.accounthistory_set.all()
        return sum(ob.xp_earned for ob in qs)

class AccountHistory(models.Model):
    account = models.ForeignKey('PlayerAccount')
    entry = models.ForeignKey('RosterEntry')
    xp_earned = models.SmallIntegerField(default=0, blank=0)
    gm_notes = models.TextField(blank=True, null=True)
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)

def setup_accounts():
    active = RosterEntry.objects.filter(roster__name__iexact="active")
    for ob in active:
        email = ob.player.email
        try:
            ob.current_account = PlayerAccount.objects.get(email=email)
        except Exception:
            ob.current_account = PlayerAccount.objects.create(email=email)
        ob.save()
        date = datetime.now()
        if not AccountHistory.objects.filter(account=ob.current_account, entry=ob):
            AccountHistory.objects.create(entry=ob, account=ob.current_account, start_date=date)


class RPScene(models.Model):
    """
    Player-uploaded, non-GM'd scenes, for them posting logs and the like.
    Log is saved in just a textfield rather than going through the trouble
    of sanitizing an uploaded and stored text file.
    """
    character = models.ForeignKey('RosterEntry', related_name='logs')
    title = models.CharField("title of the scene", max_length=80)
    synopsis = models.TextField("Description of the scene written by player")
    date = models.DateTimeField(blank=True, null=True)
    log = models.TextField("Text log of the scene")
    lock_storage = models.TextField('locks', blank=True, help_text='defined in setup_utils')
    milestone = models.OneToOneField('Milestone', related_name='log', blank=True, null=True,
                                     on_delete=models.SET_NULL)
    def __init__(self, *args, **kwargs):
        super(RPScene, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)

    class Meta:
        "Define Django meta options"
        verbose_name_plural = "RP Scenes"

    def __unicode__(self):
        return self.title

    def access(self, accessing_obj, access_type='show_hidden', default=False):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)

class Mystery(models.Model):
    name = models.CharField(max_length=255)
    desc = models.TextField("Description", help_text="Description of the mystery given to the player when fully revealed",
                            blank=True)
    category = models.CharField(help_text="Type of mystery this is - ability-related, metaplot, etc", max_length=80,
                                blank=True)
    characters = models.ManyToManyField('RosterEntry', blank=True, through='MysteryDiscovery',
                                        through_fields=('mystery', 'character'))
    class Meta:
        verbose_name_plural = "Mysteries"
    def __str__(self):
        return self.name

class Revelation(models.Model):
    name = models.CharField(max_length=255, blank=True)
    desc = models.TextField("Description", help_text="Description of the revelation given to the player",
                            blank=True)
    mysteries = models.ManyToManyField("Mystery", through='RevelationForMystery')
    
    required_clue_value = models.PositiveSmallIntegerField(default=0, blank=0,
                                                           help_text="The total value of clues to trigger this")
    
    red_herring = models.BooleanField(default=False, help_text="Whether this revelation is totally fake")
    characters = models.ManyToManyField('RosterEntry', blank=True, through='RevelationDiscovery',
                                        through_fields=('revelation', 'character'))
    def __str__(self):
        return self.name

class Clue(models.Model):
    name = models.CharField(max_length=255, blank=True)
    rating = models.PositiveSmallIntegerField(default=0, blank=0, help_text="Value required to get this clue")
    desc = models.TextField("Description", help_text="Description of the clue given to the player",
                            blank=True)
    revelations = models.ManyToManyField("Revelation", through='ClueForRevelation')
    characters = models.ManyToManyField('RosterEntry', blank=True, through='ClueDiscovery',
                                        through_fields=('clue', 'character'))
    red_herring = models.BooleanField(default=False, help_text="Whether this revelation is totally fake")
    allow_investigation = models.BooleanField(default=False, help_text="Can be gained through investigation rolls")
    allow_exploration = models.BooleanField(default=False, help_text="Can be gained through exploration rolls")
    allow_trauma = models.BooleanField(default=False, help_text="Can be gained through combat rolls")
    investigation_tags = models.TextField("Keywords for investigation", blank=True,
                                          help_text="List keywords separated by semicolons for investigation")
    def __str__(self):
        return self.name

    @property
    def keywords(self):
        return self.investigation_tags.split(";")

class MysteryDiscovery(models.Model):
    character = models.ForeignKey('RosterEntry', related_name="mysteries") 
    mystery = models.ForeignKey('Mystery', related_name="discoveries")
    investigation = models.ForeignKey('Investigation', blank=True, null=True, related_name="mysteries")
    message = models.TextField(blank=True, help_text="Message for the player's records about how they discovered this.")
    date = models.DateTimeField(blank=True, null=True)
    milestone = models.OneToOneField('Milestone', related_name="mystery", blank=True, null=True)

class RevelationDiscovery(models.Model):
    character = models.ForeignKey('RosterEntry', related_name="revelations") 
    revelation = models.ForeignKey('Revelation', related_name="discoveries")
    investigation = models.ForeignKey('Investigation', blank=True, null=True, related_name="revelations")
    message = models.TextField(blank=True, help_text="Message for the player's records about how they discovered this.")
    date = models.DateTimeField(blank=True, null=True)
    milestone = models.OneToOneField('Milestone', related_name="revelation", blank=True, null=True)
    discovery_method = models.CharField(help_text="How this was discovered - exploration, trauma, etc", max_length=255)
    revealed_by = models.ForeignKey('RosterEntry', related_name="revelations_spoiled", blank=True, null=True)
    def check_mystery_discovery(self):
        """
        For the mystery, make sure that we have all the revelations required
        inside the character before we award it to the character
        """
        # get our RevForMystery where the player does not yet have the mystery, and the rev is required
        rev_usage = self.revelation.usage.filter(required_for_mystery=True).exclude(mystery__discoveries__in=self.character.mysteries.all()).distinct()
        # get the associated mysteries the player doesn't yet have
        mysteries = Mystery.objects.filter(revelations_used__in=rev_usage)
        mysts = []
        char_revs = self.character.revelations.all()
        for myst in mysteries:
            for _rev_usage in myst.revelations_used.filter(required_for_mystery=True):
                if _rev_usage.revelation not in char_revs:
                    # character missing required revelation, can't discover
                    continue
            # character now has all revelations, we add the mystery
            mysts.append(myst)
        return mysts

class RevelationForMystery(models.Model):
    mystery = models.ForeignKey('Mystery', related_name="revelations_used")
    revelation = models.ForeignKey('Revelation', related_name="usage")
    required_for_mystery = models.BooleanField(default=True, help_text="Whether this must be discovered for the mystery to finish")
    tier = models.PositiveSmallIntegerField(default=0, blank=0,
                                            help_text="How high in the hierarchy of discoveries this revelation is, lower number discovered first")
    
class ClueDiscovery(models.Model):
    clue = models.ForeignKey('Clue', related_name="discoveries")
    character = models.ForeignKey('RosterEntry', related_name="clues")
    investigation = models.ForeignKey('Investigation', blank=True, null=True, related_name="clues")
    message = models.TextField(blank=True, help_text="Message for the player's records about how they discovered this.")
    date = models.DateTimeField(blank=True, null=True)
    milestone = models.OneToOneField('Milestone', related_name="clue", blank=True, null=True)
    discovery_method = models.CharField(help_text="How this was discovered - exploration, trauma, etc", max_length=255)
    roll = models.PositiveSmallIntegerField(default=0, blank=0)
    revealed_by = models.ForeignKey('RosterEntry', related_name="clues_spoiled", blank=True, null=True)

    @property
    def name(self):
        return self.clue.name
    
    @property
    def finished(self):
        return self.roll >= self.clue.rating

    def display(self):
        if not self.finished:
            return self.message or "An investigation that hasn't yet yieled anything defininite."
        msg = self.clue.name + "\n"
        msg += self.clue.desc + "\n"
        if self.message:
            msg += "\n" + self.message
        return msg

    def check_revelation_discovery(self):
        """
        If this Clue discovery means that the character now has every clue
        for the revelation, we award it to them.
        """
        # get our ClueForRevelations where the player does not yet have the revelation, and the clue is required
        clue_usage = self.clue.usage.filter(required_for_revelation=True).exclude(revelation__discoveries__in=self.character.revelations.all()).distinct()
        # get the associated revelations the player doesn't yet have
        revelations = Revelation.objects.filter(clues_used__in=clue_usage)
        revs = []
        char_clues = self.character.clues.all()
        for rev in revelations:
            for clue_usage in rev.clues_used.filter(required_for_revelation=True):
                if clue_usage.clue not in char_clues:
                    # character missing required clue, can't discover
                    continue
            # character now has all clues, we add the revelation
            revs.append(rev)
        return revs

    def __str__(self):
        return "%s's discovery of %s" % (self.character, self.clue)

    @property
    def progress_percentage(self):
        try:
            return self.clue.rating/self.roll
        except Exception:
            return 0

    def share(self, entry):
        """
        Copy this clue to target entry. If they already have the
        discovery, we'll add our roll to theirs (which presumably should
        finish it). If not, they'll get a copy with their roll value
        equal to ours. We'll check for them getting a revelation discovery.
        """
        try:
            targ_clue = entry.clues.get(clue=self.clue)
        except ClueDiscovery.DoesNotExist:
            targ_clue = entry.clues.create(clue=self.clue)
        if targ_clue in entry.finished_clues:
            entry.player.inform("%s tried to share the clue %s with you, but you already know that." % (self.character, self.name),
                                category="Investigations")
            return
        targ_clue.roll += self.roll
        targ_clue.discovery_method = "Sharing"
        targ_clue.message = "This clue was shared to you by %s." % self.character
        targ_clue.revealed_by = self.character
        targ_clue.date = datetime.now()
        targ_clue.save()
        pc = targ_clue.character.player
        msg = "A new clue has been shared with you by %s!\n\n%s\n" % (self.character,
                                                                    targ_clue.display())
        for revelation in targ_clue.check_revelation_discovery():
            msg += "\nYou have also discovered a revelation: %s" % str(revelation)
            rev = RevelationDiscovery.objects.create(character=entry,
                                                     discovery_method="Sharing",
                                                     message="You had a revelation after learning a clue from %s!" % self.character,
                                                     revelation=revelation, date=datetime.now())
            mysteries = rev.check_mystery_discovery()
            for mystery in mysteries:
                msg += "\nYou have also discovered a mystery: %s" % str(mystery)
                myst = MysteryDiscovery.objects.create(character=self.character,
                                                       message="Your uncovered a mystery after learning a clue from %s!" % self.character,
                                                       mystery=mystery, date=datetime.now())
        pc.inform(msg, category="Investigations", append=False)

class ClueForRevelation(models.Model):
    clue = models.ForeignKey('Clue', related_name="usage")
    revelation = models.ForeignKey('Revelation', related_name="clues_used")
    required_for_revelation = models.BooleanField(default=True, help_text="Whether this must be discovered for the revelation to finish")
    tier = models.PositiveSmallIntegerField(default=0, blank=0,
                                            help_text="How high in the hierarchy of discoveries this clue is, lower number discovered first")

class Investigation(models.Model):
    character = models.ForeignKey('RosterEntry', related_name="investigations")
    ongoing = models.BooleanField(default=True, help_text="Whether this investigation is finished or not")
    active = models.BooleanField(default=False, help_text="Whether this is the investigation for the week. Only one allowed")
    automate_result = models.BooleanField(default=True, help_text="Whether to generate a result during weekly maintenance. Set false if GM'd")
    results = models.TextField(default="You didn't find anything.", blank=True,
                               help_text="The text to send the player, either set by GM or generated automatically " +
                               "by script if automate_result is set.")
    clue_target = models.ForeignKey('Clue', blank=True, null=True)
    actions = models.TextField(blank=True, help_text="The writeup the player submits of their actions, used for GMing.")
    topic = models.CharField(blank=True, max_length=255, help_text="Keyword to try to search for clues against")
    stat_used = models.CharField(blank=True, max_length=80, default="perception", help_text="The stat the player chose to use")
    skill_used = models.CharField(blank=True, max_length=80, default="investigation", help_text="The skill the player chose to use")
    silver = models.PositiveSmallIntegerField(default=0, blank=0, help_text="Additional silver added by the player")
    economic = models.PositiveSmallIntegerField(default=0, blank=0, help_text="Additional economic resources added by the player")
    military = models.PositiveSmallIntegerField(default=0, blank=0, help_text="Additional military resources added by the player")
    social = models.PositiveSmallIntegerField(default=0, blank=0, help_text="Additional social resources added by the player")

    def __str__(self):
        return "%s's investigation on %s" % (self.character, self.topic)

    def display(self):
        msg = ""
        msg = "{wCharacter{n: %s\n" % self.character
        msg += "{wTopic{n: %s\n" % self.topic
        msg += "{wActions{n:\n%s\n" % self.actions
        msg += "{wModified Difficulty{n: %s\n" % self.difficulty
        msg += "{wCurrent Progress{n: %s\n" % self.progress_str
        msg += "{wStat used{n: %s\n" % self.stat_used
        msg += "{wSkill used{n: %s\n" % self.skill_used
        return msg

    def gm_display(self):
        msg = self.display()
        msg += "{wCurrent Roll{n: %s\n" % self.roll
        msg += "{wTargeted Clue{n: %s\n" % self.targeted_clue
        msg += "{wProgress Value{n: %s\n" % self.progress
        msg += "{wComplete this week?{n: %s\n" % self.check_success()
        return msg

    @property
    def char(self):
        return self.character.character
    
    def do_roll(self, mod=0, diff=None):
        """
        Do a dice roll to return a result
        """
        from world.stats_and_skills import do_dice_check
        char = self.char
        diff = (diff if diff != None else self.difficulty) + mod
        roll = do_dice_check(char, stat_list=[self.stat_used, "perception"], skill_list=[self.skill_used, "investigation"],
                             difficulty=diff, average_lists=True)
        # save the character's roll
        self.roll = roll
        return roll

    @property
    def resource_mod(self):
        mod = 0
        silvermod = self.silver/5000
        if silvermod > 10:
            silvermod = 10
        mod += silvermod
        resmod = (self.economic + self.military + self.social)/5
        if resmod > 30:
            resmod = 30
        mod += resmod
        return mod
        

    def _get_roll(self):
        char = self.char
        try:
            return int(char.db.investigation_roll)
        except (ValueError, TypeError):
            return self.do_roll()
        
    def _set_roll(self, value):
        char = self.char
        char.db.investigation_roll = int(value)
    roll = property(_get_roll, _set_roll)
    
    @property
    def difficulty(self):
        """
        Determine our difficulty based on our expenditures and the clue
        we're trying to uncover.
        """
        if not self.automate_result or not self.targeted_clue:
            base = 30 # base difficulty for things without clues
        else:
            base = 20 + (self.targeted_clue.rating)
        return base - self.resource_mod

    @property
    def completion_value(self):
        if not self.targeted_clue:
            return 30
        return self.targeted_clue.rating
    
    def check_success(self, modifier=0, diff=None):
        """
        Checks success. Modifier can be passed by a GM based on their
        discretion, but otherwise is 0. diff is passed if we don't
        want to find a targeted clue and generate our difficulty based
        on that.
        """
        if diff != None:
            return (self.roll + self.progress) >= (diff + modifier)
        return (self.roll + self.progress) >= (self.completion_value)

    def process_events(self):
        self.generate_result()
        self.use_resources()
        # wipe the stale roll
        self.char.attributes.remove("investigation_roll")
        msg = "Your investigation into '%s' has had the following result:\n" % self.topic
        msg += self.results
        self.character.player.inform(msg, category="Investigations")

    def generate_result(self):
        """
        If we aren't GMing this, check success then set the results string
        accordingly.
        """
        if self.check_success():
            # if we don't have a valid clue, then let's
            # tell them about what a valid clue -could- be.
            if not self.targeted_clue and self.automate_result:
                kw = self.find_random_keywords()
                if not kw:
                    self.results = "There is nothing else for you to find."
                else:
                    self.results = "You couldn't find anything about '%s', " % self.topic
                    self.results += "but you keep on finding mention of '%s' in your search." % kw
            else:
                # add a valid clue and update results string
                roll = self.roll
                try:
                    clue = self.clues.get(clue=self.targeted_clue, character=self.character)
                except ClueDiscovery.DoesNotExist:                    
                    clue = ClueDiscovery.objects.create(clue=self.targeted_clue, investigation=self,
                                                        character=self.character)
                clue.roll += roll
                if self.automate_result:
                    self.results = "Your investigation has discovered a clue!\n"
                self.results += clue.display()
                if not clue.message:
                    clue.message = "Your investigation has discovered this!"
                clue.date=datetime.now()
                clue.discovery_method="investigation"
                clue.save()
                
                # check if we also discover a revelation
                revelations = clue.check_revelation_discovery()
                for revelation in revelations:
                    self.results += "\nYou have also discovered a revelation: %s" % str(revelation)
                    rev = RevelationDiscovery.objects.create(character=self.character, investigation=self,
                                                             discovery_method="investigation",
                                                             message="Your investigation uncovered this revelation!",
                                                             revelation=revelation, date=datetime.now())
                    mysteries = rev.check_mystery_discovery()
                    for mystery in mysteries:
                        self.results += "\nYou have also discovered a mystery: %s" % str(mystery)
                        myst = MysteryDiscovery.objects.create(character=self.character, investigation=self,
                                                                 message="Your investigation uncovered this mystery!",
                                                                 mystery=mystery, date=datetime.now())
                # we found a clue, so this investigation is done.
                self.clue_target = None
                self.active = False
                self.ongoing = False          
        else:
            # update results to indicate our failure
            self.results = "Your investigation failed to find anything."
            if self.add_progress():
                self.results += " But you feel you've made some progress in following some leads."
        self.save()
        
    def use_resources(self):
        """
        Reduce the silver/resources added to this investigation.
        """
        self.silver = 0
        for res in ('economic', 'military', 'social'):
            amt = getattr(self, res)
            amt -= 50
            if amt < 0:
                amt = 0
            setattr(self, res, amt)
        self.save()

    @property
    def targeted_clue(self):
        if self.clue_target:
            return self.clue_target
        self.clue_target = self.find_target_clue()
        self.save()
        return self.clue_target

    def find_target_clue(self):
        """
        Finds a target clue based on our topic and our investigation history.
        We'll choose the lowest rating out of 3 random choices.
        """
        candidates = Clue.objects.filter(Q(investigation_tags__icontains=self.topic) &
                                         ~Q(characters=self.character)).order_by('rating')
        try:
            import random
            choices = []
            for x in range(0, 3):
                choices.append(random.randint(0, candidates.count()))
            return candidates[min(choices)]
        except IndexError:
            return None

    def find_random_keywords(self):
        """
        Finds a random keyword in a clue we don't have yet.
        """
        import random
        candidates = Clue.objects.filter(~Q(characters=self.character)).order_by('rating')
        try:
            ob = random.choice(candidates)
            kw = random.choice(ob.keywords)
            return kw
        except Exception:
            return None

    @property
    def progress(self):
        try:
            clue = self.clues.get(clue=self.targeted_clue)
            return clue.roll
        except ClueDiscovery.DoesNotExist:
            return 0

    def add_progress(self):
        if not self.targeted_clue:
            return
        roll = self.roll
        try:
            roll = int(roll)
        except (ValueError, TypeError):
            return
        try:
            clue = self.clues.get(clue=self.targeted_clue)
            clue.roll += roll
            clue.save()
        except ClueDiscovery.DoesNotExist:
            clue = ClueDiscovery.objects.create(clue=self.targeted_clue, investigation=self,
                                                roll=roll,
                                                character=self.character)
        return roll
        
    @property
    def progress_str(self):
        try:
            clue = self.clues.get(clue=self.targeted_clue)
            prog = clue.progress_percentage
        except (ClueDiscovery.DoesNotExist, AttributeError):
            prog = 0
        if prog <= 0:
            return "No real progress has been made to finding something new."
        if prog <= 25:
            return "You've made some progress."
        if prog <= 50:
            return "You've made a good amount of progress."
        if prog <= 75:
            return "You feel like you're getting close to finding something."
        return "You feel like you're on the verge of a breakthrough. You just need more time."
        
    
