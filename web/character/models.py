from django.db import models
from django.conf import settings
from cloudinary.models import CloudinaryField
from evennia.objects.models import ObjectDB
from evennia.locks.lockhandler import LockHandler
from django.db.models import Q, F
from .managers import ArxRosterManager
from datetime import datetime
import random
import traceback
from world.stats_and_skills import do_dice_check

"""
This is the main model in the project. It holds a reference to cloudinary-stored
image and contains some metadata about the image.
"""


class Photo(models.Model):
    #  Misc Django Fields
    create_time = models.DateTimeField(auto_now_add=True)
    title = models.CharField("Name or description of the picture (optional)", max_length=200, blank=True)
    owner = models.ForeignKey("objects.ObjectDB", blank=True, null=True, verbose_name='owner',
                              help_text='a Character owner of this image, if any.')
    alt_text = models.CharField("Optional 'alt' text when mousing over your image", max_length=200, blank=True)

    # Points to a Cloudinary image
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
    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
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
                               on_delete=models.SET_NULL, blank=True, null=True, db_index=True)
    player = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='roster', blank=True, null=True, unique=True)
    character = models.OneToOneField('objects.ObjectDB', related_name='roster', blank=True, null=True, unique=True)
    current_account = models.ForeignKey('PlayerAccount', related_name='characters', db_index=True,
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
        """Define Django meta options"""
        verbose_name_plural = "Roster Entries"
        unique_together = ('player', 'character')

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
            del_roster = Roster.objects.get(name__iexact="Deleted")
        except Roster.DoesNotExist:
            print("Could not find Deleted Roster!")
            return
        self.roster = del_roster
        self.inactive = True
        self.frozen = True
        self.save()

    def undelete(self, r_name="Active"):
        try:
            roster = Roster.objects.get(name__iexact=r_name)
        except Roster.DoesNotExist:
            print("Could not find %s roster!" % r_name)
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
        except (AccountHistory.DoesNotExist, AccountHistory.MultipleObjectsReturned):
            pass

    @property
    def finished_clues(self):
        return self.clues.filter(roll__gte=F('clue__rating'))

    @property
    def alts(self):
        if self.current_account:
            return self.current_account.characters.exclude(id=self.id)
        return []

    def discover_clue(self, clue):
        try:
            disco = self.clues.get(clue=clue)
        except ClueDiscovery.DoesNotExist:
            disco = self.clues.create(clue=clue)
        except ClueDiscovery.MultipleObjectsReturned:
            disco = self.clues.filter(clue=clue)[0]
        disco.roll = disco.clue.rating
        disco.date = datetime.now()
        disco.discovery_method = "Prior Knowledge"
        disco.save()
        return disco


class Story(models.Model):
    current_chapter = models.OneToOneField('Chapter', related_name='current_chapter_story',
                                           on_delete=models.SET_NULL, blank=True, null=True, db_index=True)
    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    synopsis = models.TextField(blank=True, null=True)
    season = models.PositiveSmallIntegerField(default=0, blank=0)
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Stories"

    def __str__(self):
        return self.name or "Story object"


class Chapter(models.Model):
    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    synopsis = models.TextField(blank=True, null=True)
    story = models.ForeignKey('Story', blank=True, null=True, db_index=True,
                              on_delete=models.SET_NULL, related_name='previous_chapters')
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name or "Chapter object"


class Episode(models.Model):
    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    chapter = models.ForeignKey('Chapter', blank=True, null=True,
                                on_delete=models.SET_NULL, related_name='episodes', db_index=True)
    synopsis = models.TextField(blank=True, null=True)
    gm_notes = models.TextField(blank=True, null=True)
    date = models.DateTimeField(blank=True, null=True, db_index=True)

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
    account = models.ForeignKey('PlayerAccount', db_index=True)
    entry = models.ForeignKey('RosterEntry', db_index=True)
    xp_earned = models.SmallIntegerField(default=0, blank=0)
    gm_notes = models.TextField(blank=True, null=True)
    start_date = models.DateTimeField(blank=True, null=True, db_index=True)
    end_date = models.DateTimeField(blank=True, null=True, db_index=True)


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
        """Define Django meta options"""
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
    name = models.CharField(max_length=255, db_index=True)
    desc = models.TextField("Description", help_text="Description of the mystery given to the player " +
                                                     "when fully revealed",
                            blank=True)
    category = models.CharField(help_text="Type of mystery this is - ability-related, metaplot, etc", max_length=80,
                                blank=True)
    characters = models.ManyToManyField('RosterEntry', blank=True, through='MysteryDiscovery',
                                        through_fields=('mystery', 'character'), db_index=True)

    class Meta:
        verbose_name_plural = "Mysteries"

    def __str__(self):
        return self.name


class Revelation(models.Model):
    name = models.CharField(max_length=255, blank=True, db_index=True)
    desc = models.TextField("Description", help_text="Description of the revelation given to the player",
                            blank=True)
    mysteries = models.ManyToManyField("Mystery", through='RevelationForMystery')
    
    required_clue_value = models.PositiveSmallIntegerField(default=0, blank=0,
                                                           help_text="The total value of clues to trigger this")
    
    red_herring = models.BooleanField(default=False, help_text="Whether this revelation is totally fake")
    characters = models.ManyToManyField('RosterEntry', blank=True, through='RevelationDiscovery',
                                        through_fields=('revelation', 'character'), db_index=True)

    def __str__(self):
        return self.name

    def check_progress(self, char):
        """
        Returns the total value of the clues used for this revelation by
        char.
        """
        return sum(ob.clue.rating for ob in char.finished_clues.filter(clue__revelations=self))


class Clue(models.Model):
    name = models.CharField(max_length=255, blank=True, db_index=True)
    rating = models.PositiveSmallIntegerField(default=0, blank=0, help_text="Value required to get this clue",
                                              db_index=True)
    desc = models.TextField("Description", help_text="Description of the clue given to the player",
                            blank=True)
    revelations = models.ManyToManyField("Revelation", through='ClueForRevelation', db_index=True)
    characters = models.ManyToManyField('RosterEntry', blank=True, through='ClueDiscovery', db_index=True,
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
        return self.investigation_tags.lower().split(";")


class MysteryDiscovery(models.Model):
    character = models.ForeignKey('RosterEntry', related_name="mysteries", db_index=True)
    mystery = models.ForeignKey('Mystery', related_name="discoveries", db_index=True)
    investigation = models.ForeignKey('Investigation', blank=True, null=True, related_name="mysteries")
    message = models.TextField(blank=True, help_text="Message for the player's records about how they discovered this.")
    date = models.DateTimeField(blank=True, null=True)
    milestone = models.OneToOneField('Milestone', related_name="mystery", blank=True, null=True)

    class Meta:
        unique_together = ('character', 'mystery')
        verbose_name_plural = "Mystery Discoveries"

    def __str__(self):
        return "%s's discovery of %s" % (self.character, self.mystery)


class RevelationDiscovery(models.Model):
    character = models.ForeignKey('RosterEntry', related_name="revelations", db_index=True)
    revelation = models.ForeignKey('Revelation', related_name="discoveries", db_index=True)
    investigation = models.ForeignKey('Investigation', blank=True, null=True, related_name="revelations")
    message = models.TextField(blank=True, help_text="Message for the player's records about how they discovered this.")
    date = models.DateTimeField(blank=True, null=True)
    milestone = models.OneToOneField('Milestone', related_name="revelation", blank=True, null=True)
    discovery_method = models.CharField(help_text="How this was discovered - exploration, trauma, etc", max_length=255)
    revealed_by = models.ForeignKey('RosterEntry', related_name="revelations_spoiled", blank=True, null=True)

    class Meta:
        unique_together = ('character', 'revelation')
        verbose_name_plural = "Revelation Discoveries"

    def check_mystery_discovery(self):
        """
        For the mystery, make sure that we have all the revelations required
        inside the character before we award it to the character
        """
        # get our RevForMystery where the player does not yet have the mystery, and the rev is required
        rev_usage = self.revelation.usage.filter(required_for_mystery=True).distinct()
        # get the associated mysteries the player doesn't yet have
        mysteries = Mystery.objects.filter(Q(revelations_used__in=rev_usage) &
                                           ~Q(characters=self.character)).distinct()
        discoveries = []
        char_revs = set([ob.revelation for ob in self.character.revelations.all()])
        for myst in mysteries:
            required_revs = set([ob.revelation for ob in myst.revelations_used.filter(required_for_mystery=True)])
            # character now has all revelations, we add the mystery
            if required_revs.issubset(char_revs):
                discoveries.append(myst)
        return discoveries

    def __str__(self):
        return "%s's discovery of %s" % (self.character, self.revelation)

    def display(self):
        msg = self.revelation.name + "\n"
        msg += self.revelation.desc + "\n"
        if self.message:
            msg += "\n" + self.message
        return msg


class RevelationForMystery(models.Model):
    mystery = models.ForeignKey('Mystery', related_name="revelations_used", db_index=True)
    revelation = models.ForeignKey('Revelation', related_name="usage", db_index=True)
    required_for_mystery = models.BooleanField(default=True, help_text="Whether this must be discovered for the" +
                                                                       " mystery to finish")
    tier = models.PositiveSmallIntegerField(default=0, blank=0,
                                            help_text="How high in the hierarchy of discoveries this revelation is," +
                                                      " lower number discovered first")

    def __str__(self):
        return "Revelation %s used for %s" % (self.revelation, self.mystery)


class ClueDiscovery(models.Model):
    clue = models.ForeignKey('Clue', related_name="discoveries", db_index=True)
    character = models.ForeignKey('RosterEntry', related_name="clues", db_index=True)
    investigation = models.ForeignKey('Investigation', blank=True, null=True, related_name="clues", db_index=True)
    message = models.TextField(blank=True, help_text="Message for the player's records about how they discovered this.")
    date = models.DateTimeField(blank=True, null=True)
    milestone = models.OneToOneField('Milestone', related_name="clue", blank=True, null=True)
    discovery_method = models.CharField(help_text="How this was discovered - exploration, trauma, etc", max_length=255)
    roll = models.PositiveSmallIntegerField(default=0, blank=0, db_index=True)
    revealed_by = models.ForeignKey('RosterEntry', related_name="clues_spoiled", blank=True, null=True, db_index=True)

    class Meta:
        verbose_name_plural = "Clue Discoveries"

    @property
    def name(self):
        return self.clue.name

    @property
    def finished(self):
        return self.roll >= self.clue.rating

    def display(self):
        if not self.finished:
            return self.message or "An investigation that hasn't yet yielded anything definite."
        msg = "\n{c%s{n\n" % self.clue.name
        msg += self.clue.desc + "\n"
        if self.message:
            msg += "\n" + self.message
        shared = self.shared_with
        if shared:
            msg += "\n{wShared with{n: %s" % ", ".join(str(ob) for ob in shared)
        return msg

    def check_revelation_discovery(self):
        """
        If this Clue discovery means that the character now has every clue
        for the revelation, we award it to them.
        """
        # find all ClueForRevelations used for this discovery
        clue_usage = self.clue.usage.all()
        # get the associated revelations the player doesn't yet have
        revelations = Revelation.objects.filter(Q(clues_used__in=clue_usage) &
                                                ~Q(characters=self.character))
        discovered = []
        char_clues = set([ob.clue for ob in self.character.finished_clues])
        for rev in revelations:
            used_clues = set([ob.clue for ob in rev.clues_used.filter(required_for_revelation=True)])
            # check if we have all the required clues for this revelation discovered
            if used_clues.issubset(char_clues):
                # check if we have enough numerical value of clues to pass
                if rev.check_progress(self.character) >= rev.required_clue_value:
                    discovered.append(rev)
        return discovered

    def __str__(self):
        return "%s's discovery of %s" % (self.character, self.clue)

    @property
    def progress_percentage(self):
        try:
            return int((float(self.roll) / float(self.clue.rating)) * 100)
        except (AttributeError, TypeError, ValueError, ZeroDivisionError):
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
        except ClueDiscovery.MultipleObjectsReturned:
            clues = entry.clues.filter(clue=self.clue).order_by('-roll')
            targ_clue = clues[0]
            for clue in clues:
                if clue != targ_clue:
                    clue.delete()
        if targ_clue in entry.finished_clues:
            entry.player.send_or_queue_msg("%s tried to share the clue %s with you, but you already know that." % (
                self.character, self.name))
            return
        investigations = entry.investigations.filter(clue_target=self.clue)
        for investigation in investigations:
            investigation.clue_target = None
            investigation.save()
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
            msg += "\nYou have also discovered a revelation: %s\n%s" % (str(revelation), revelation.desc)
            message = "You had a revelation after learning a clue from %s!" % self.character
            rev = RevelationDiscovery.objects.create(character=entry,
                                                     discovery_method="Sharing",
                                                     message=message,
                                                     revelation=revelation, date=datetime.now())
            mysteries = rev.check_mystery_discovery()
            for mystery in mysteries:
                msg += "\nYou have also discovered a mystery: %s\n%s" % (str(mystery), mystery.desc)
                message = "Your uncovered a mystery after learning a clue from %s!" % self.character,
                MysteryDiscovery.objects.create(character=self.character,
                                                message=message,
                                                mystery=mystery, date=datetime.now())
        pc.inform(msg, category="Investigations", append=False)

    @property
    def shared_with(self):
        spoiled = self.character.clues_spoiled.filter(clue=self.clue)
        return RosterEntry.objects.filter(clues__in=spoiled)


class ClueForRevelation(models.Model):
    clue = models.ForeignKey('Clue', related_name="usage", db_index=True)
    revelation = models.ForeignKey('Revelation', related_name="clues_used", db_index=True)
    required_for_revelation = models.BooleanField(default=True, help_text="Whether this must be discovered for " +
                                                                          "the revelation to finish")
    tier = models.PositiveSmallIntegerField(default=0, blank=0,
                                            help_text="How high in the hierarchy of discoveries this clue is, " +
                                                      "lower number discovered first")

    def __str__(self):
        return "Clue %s used for %s" % (self.clue, self.revelation)


class InvestigationAssistant(models.Model):
    currently_helping = models.BooleanField(default=True, help_text="Whether they're currently helping out")
    investigation = models.ForeignKey('Investigation', related_name="assistants", db_index=True)
    char = models.ForeignKey('objects.ObjectDB', related_name="assisted_investigations", db_index=True)
    stat_used = models.CharField(blank=True, max_length=80, default="perception",
                                 help_text="The stat the player chose to use")
    skill_used = models.CharField(blank=True, max_length=80, default="investigation",
                                  help_text="The skill the player chose to use")
    actions = models.TextField(blank=True, help_text="The writeup the player submits of their actions, used for GMing.")

    def __str__(self):
        return "%s helping: %s" % (self.char, self.investigation)

    def shared_discovery(self, clue):
        self.currently_helping = False
        self.save()
        try:
            clue.share(self.char.roster)
        except AttributeError:
            pass
        

class Investigation(models.Model):
    character = models.ForeignKey('RosterEntry', related_name="investigations", db_index=True)
    ongoing = models.BooleanField(default=True, help_text="Whether this investigation is finished or not",
                                  db_index=True)
    active = models.BooleanField(default=False, db_index=True, help_text="Whether this is the investigation for the" +
                                                                         " week. Only one allowed")
    automate_result = models.BooleanField(default=True, help_text="Whether to generate a result during weekly " +
                                                                  "maintenance. Set false if GM'd")
    results = models.TextField(default="You didn't find anything.", blank=True,
                               help_text="The text to send the player, either set by GM or generated automatically " +
                               "by script if automate_result is set.")
    clue_target = models.ForeignKey('Clue', blank=True, null=True)
    actions = models.TextField(blank=True, help_text="The writeup the player submits of their actions, used for GMing.")
    topic = models.CharField(blank=True, max_length=255, help_text="Keyword to try to search for clues against")
    stat_used = models.CharField(blank=True, max_length=80, default="perception",
                                 help_text="The stat the player chose to use")
    skill_used = models.CharField(blank=True, max_length=80, default="investigation",
                                  help_text="The skill the player chose to use")
    silver = models.PositiveSmallIntegerField(default=0, blank=0, help_text="Additional silver added by the player")
    economic = models.PositiveSmallIntegerField(default=0, blank=0,
                                                help_text="Additional economic resources added by the player")
    military = models.PositiveSmallIntegerField(default=0, blank=0,
                                                help_text="Additional military resources added by the player")
    social = models.PositiveSmallIntegerField(default=0, blank=0,
                                              help_text="Additional social resources added by the player")

    def __str__(self):
        return "%s's investigation on %s" % (self.character, self.topic)

    def display(self):
        msg = "{wCharacter{n: %s\n" % self.character
        msg += "{wTopic{n: %s\n" % self.topic
        msg += "{wActions{n: %s\n" % self.actions
        msg += "{wModified Difficulty{n: %s\n" % self.difficulty
        msg += "{wCurrent Progress{n: %s\n" % self.progress_str
        msg += "{wStat used{n: %s\n" % self.stat_used
        msg += "{wSkill used{n: %s\n" % self.skill_used
        for assistant in self.active_assistants:
            msg += "{wAssistant:{n %s {wStat:{n %s {wSkill:{n %s {wActions:{n %s\n" % (
                assistant.char, assistant.stat_used, assistant.skill_used, assistant.actions)
        return msg

    def gm_display(self):
        msg = self.display()
        msg += "{wCurrent Roll{n: %s\n" % self.roll
        msg += "{wTargeted Clue{n: %s\n" % self.targeted_clue
        msg += "{wProgress Value{n: %s\n" % self.progress
        msg += "{wComplete this week?{n: %s\n" % self.check_success()
        msg += "{wSilver Used{n: %s\n" % self.silver
        msg += "{wEconomic Used{n %s\n" % self.economic
        msg += "{wMilitary Used{n %s\n" % self.military
        msg += "{wSocial Used{n %s\n" % self.social
        return msg

    @property
    def char(self):
        return self.character.character

    @property
    def active_assistants(self):
        return self.assistants.filter(currently_helping=True)

    @staticmethod
    def do_obj_roll(obj, diff):
        """
        Method that takes either an investigation or one of its
        assistants and returns a dice roll based on its character,
        and the stats/skills used by that investigation or assistant.
        """
        stat = obj.stat_used or "perception"
        stat = stat.lower()
        skill = obj.skill_used or "investigation"
        skill = skill.lower()
        roll = do_dice_check(obj.char, stat_list=[stat, "perception"], skill_list=[skill, "investigation"],
                             difficulty=diff, average_lists=True)
        return roll
    
    def do_roll(self, mod=0, diff=None):
        """
        Do a dice roll to return a result
        """
        diff = (diff if diff is not None else self.difficulty) + mod
        roll = self.do_obj_roll(self, diff)
        for ass in self.active_assistants:
            a_roll = self.do_obj_roll(ass, diff)
            if a_roll < 0:
                a_roll = 0
            try:
                ability_level = ass.char.db.abilities['investigation_assistant']
            except (AttributeError, ValueError, KeyError):
                ability_level = 0
            a_roll += random.randint(0, 5) * ability_level
            roll += a_roll
        # save the character's roll
        print("final roll is %s" % roll)
        self.roll = roll
        return roll

    @property
    def resource_mod(self):
        mod = 0
        silver_mod = self.silver/2500
        if silver_mod > 20:
            silver_mod = 20
        mod += silver_mod
        res_mod = int((self.economic + self.military + self.social)/2.5)
        if random.randint(0, 5) < (self.economic + self.military + self.social) % 5:
            res_mod += 1
        if res_mod > 60:
            res_mod = 60
        mod += res_mod
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
            base = 30  # base difficulty for things without clues
        else:
            base = self.targeted_clue.rating
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
        if diff is not None:
            return (self.roll + self.progress) >= (diff + modifier)
        return (self.roll + self.progress) >= self.completion_value

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
                clue.date = datetime.now()
                clue.discovery_method = "investigation"
                clue.save()
                
                # check if we also discover a revelation
                revelations = clue.check_revelation_discovery()
                for revelation in revelations:
                    self.results += "\nYou have also discovered a revelation: %s\n%s" % (str(revelation),
                                                                                         revelation.desc)
                    rev = RevelationDiscovery.objects.create(character=self.character, investigation=self,
                                                             discovery_method="investigation",
                                                             message="Your investigation uncovered this revelation!",
                                                             revelation=revelation, date=datetime.now())
                    mysteries = rev.check_mystery_discovery()
                    for mystery in mysteries:
                        self.results += "\nYou have also discovered a mystery: %s\n%s" % (str(mystery), mystery.desc)
                        MysteryDiscovery.objects.create(character=self.character, investigation=self,
                                                        message="Your investigation uncovered this mystery!",
                                                        mystery=mystery, date=datetime.now())
                # we found a clue, so this investigation is done.
                self.clue_target = None
                self.active = False
                self.ongoing = False
                for ass in self.active_assistants:
                    # noinspection PyBroadException
                    try:
                        ass.shared_discovery(clue)
                    except Exception:
                        traceback.print_exc()
        else:
            # update results to indicate our failure
            self.results = "Your investigation failed to find anything."
            if self.add_progress():
                self.results += " But you feel you've made some progress in following some leads."
            else:
                self.results += " None of your leads seemed to go anywhere this week."
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

    @property
    def keywords(self):
        k_words = [str(ob) for ob in self.topic.lower().split()]
        # add back in the phrases for phrase matching
        if len(k_words) > 1:
            for pos in range(0, len(k_words)):
                phrase = []
                for s_pos in range(0, pos):
                    phrase.append(k_words[s_pos])
                k_words.append(" ".join(phrase))
        for word in ("a", "or", "an", "the", "and", "but", "not",
                     "yet", "with", "in", "how", "if", "of"):
            if word in k_words:
                k_words.remove(str(word))
        if self.topic.lower() not in k_words:
            k_words.append(str(self.topic.lower()))
        return k_words

    def find_target_clue(self):
        """
        Finds a target clue based on our topic and our investigation history.
        We'll choose the lowest rating out of 3 random choices.
        """
        k_words = self.keywords
        candidates = Clue.objects.filter(Q(investigation_tags__icontains=self.topic) &
                                         ~Q(characters=self.character)).order_by('rating')
        for k_word in k_words:
            qs = Clue.objects.filter(Q(investigation_tags__icontains=k_word) &
                                     ~Q(characters=self.character)).order_by('rating')
            candidates = candidates | qs
        try:
            candidates = [ob for ob in candidates if any(set(k_words) & set(ob.keywords))]
            choices = []
            for x in range(0, 3):
                choices.append(random.randint(0, len(candidates) - 1))
            return candidates[min(choices)]
        except (IndexError, ValueError):
            return None

    def find_random_keywords(self):
        """
        Finds a random keyword in a clue we don't have yet.
        """
        candidates = Clue.objects.filter(~Q(characters=self.character)).order_by('rating')
        # noinspection PyBroadException
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

    @property
    def goal(self):
        try:
            clue = self.clues.get(clue=self.targeted_clue)
            return clue.clue.rating
        except (ClueDiscovery.DoesNotExist, Clue.DoesNotExist, AttributeError):
            return 0

    def add_progress(self):
        if not self.targeted_clue:
            return
        roll = self.roll
        try:
            roll = int(roll)
        except (ValueError, TypeError):
            return
        if roll <= 0:
            return
        try:
            clue = self.clues.get(clue=self.targeted_clue)
            clue.roll += roll
            clue.save()
        except ClueDiscovery.DoesNotExist:
            ClueDiscovery.objects.create(clue=self.targeted_clue, investigation=self,
                                         roll=roll,
                                         character=self.character)
        return roll
        
    @property
    def progress_str(self):
        try:
            clue = self.clues.get(clue=self.targeted_clue)
            progress = clue.progress_percentage
        except (ClueDiscovery.DoesNotExist, AttributeError):
            progress = 0
        if progress <= 0:
            return "No real progress has been made to finding something new."
        if progress <= 25:
            return "You've made some progress."
        if progress <= 50:
            return "You've made a good amount of progress."
        if progress <= 75:
            return "You feel like you're getting close to finding something."
        return "You feel like you're on the verge of a breakthrough. You just need more time."


class Theory(models.Model):
    """
    Represents a theory that a player has come up with, and is now
    stored and can be shared with others.
    """
    creator = models.ForeignKey("players.PlayerDB", related_name="created_theories", blank=True, null=True,
                                db_index=True)
    known_by = models.ManyToManyField("players.PlayerDB", related_name="known_theories", blank=True, null=True)
    can_edit = models.ManyToManyField("players.PlayerDB", related_name="editable_theories", blank=True, null=True)
    topic = models.CharField(max_length=255, blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    related_clues = models.ManyToManyField("Clue", related_name="theories", blank=True, null=True, db_index=True)
    related_theories = models.ManyToManyField("self", blank=True)

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Theories"

    def __str__(self):
        return "%s's theory on %s" % (self.creator, self.topic)

    def display(self):
        msg = "\n{wCreator{n: %s\n" % self.creator
        msg += "{wCan edit:{n %s\n" % ", ".join(str(ob) for ob in self.can_edit.all())
        msg += "{wTopic{n: %s\n" % self.topic
        msg += "{wDesc{n: %s\n" % self.desc
        msg += "{wRelated Theories{n: %s\n" % ", ".join(str(ob.id) for ob in self.related_theories.all())
        return msg
