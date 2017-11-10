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
from evennia.typeclasses.models import SharedMemoryModel

# multiplier for how much higher ClueDiscovery.roll must be over Clue.rating to be discovered
DISCO_MULT = 10


class Photo(SharedMemoryModel):
    """
    This is the main model in the project. It holds a reference to cloudinary-stored
    image and contains some metadata about the image.
    """
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


class Roster(SharedMemoryModel):
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


class RosterEntry(SharedMemoryModel):
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
    action_points = models.SmallIntegerField(default=100, blank=100)
    
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
        return self.clues.filter(roll__gte=F('clue__rating') * DISCO_MULT)

    @property
    def discovered_clues(self):
        return Clue.objects.filter(id__in=[ob.clue.id for ob in self.finished_clues])

    @property
    def undiscovered_clues(self):
        return Clue.objects.exclude(id__in=[ob.clue.id for ob in self.finished_clues])

    @property
    def alts(self):
        if self.current_account:
            return self.current_account.characters.exclude(id=self.id)
        return []

    def discover_clue(self, clue, method="Prior Knowledge"):
        try:
            disco = self.clues.get(clue=clue)
        except ClueDiscovery.DoesNotExist:
            disco = self.clues.create(clue=clue)
        except ClueDiscovery.MultipleObjectsReturned:
            disco = self.clues.filter(clue=clue)[0]
        disco.roll = disco.clue.rating * DISCO_MULT
        disco.date = datetime.now()
        disco.discovery_method = method
        disco.save()
        return disco

    @property
    def current_history(self):
        return self.accounthistory_set.last()

    @property
    def current_impressions(self):
        """
        Gets queryset of all our current first impressions
        """
        try:
            return self.current_history.received_contacts.all()
        except AttributeError:
            return []

    @property
    def public_impressions(self):
        try:
            return self.current_impressions.filter(private=False).order_by('from_account__entry__character__db_key')
        except AttributeError:
            return []

    @property
    def impressions_for_all(self):
        try:
            return self.public_impressions.filter(writer_share=True, receiver_share=True)
        except AttributeError:
            return []

    def get_impressions_str(self, player=None):
        qs = self.current_impressions.filter(private=False)
        if player:
            qs = qs.filter(from_account__entry__player=player)

        def public_str(obj):
            if obj.viewable_by_all:
                return "{w(Shared by Both){n"
            if obj.writer_share:
                return "{w(Marked Public by Writer){n"
            if obj.receiver_share:
                return "{w(Marked Public by You){n"
            return "{w(Private){n"
        return "\n\n".join("{c%s{n wrote %s: %s" % (ob.writer, public_str(ob),
                                                    ob.summary) for ob in qs)


class Story(SharedMemoryModel):
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


class Chapter(SharedMemoryModel):
    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    synopsis = models.TextField(blank=True, null=True)
    story = models.ForeignKey('Story', blank=True, null=True, db_index=True,
                              on_delete=models.SET_NULL, related_name='previous_chapters')
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name or "Chapter object"

    @property
    def public_crises(self):
        return self.crises.filter(public=True)

    def crises_viewable_by_user(self, user):
        if not user or not user.is_authenticated():
            return self.public_crises
        if user.is_staff or user.check_permstring("builders"):
            return self.crises.all()
        return self.crises.filter(Q(public=True) | Q(required_clue__discoveries__in=user.roster.discovered_clues))


class Episode(SharedMemoryModel):
    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    chapter = models.ForeignKey('Chapter', blank=True, null=True,
                                on_delete=models.SET_NULL, related_name='episodes', db_index=True)
    synopsis = models.TextField(blank=True, null=True)
    gm_notes = models.TextField(blank=True, null=True)
    date = models.DateTimeField(blank=True, null=True, db_index=True)

    def __str__(self):
        return self.name or "Episode object"

    @property
    def public_crisis_updates(self):
        return self.crisis_updates.filter(crisis__public=True)

    def get_viewable_crisis_updates_for_player(self, player):
        if not player or not player.is_authenticated():
            return self.public_crisis_updates
        if player.is_staff or player.check_permstring("builders"):
            return self.crisis_updates.all()
        return self.crisis_updates.filter(Q(crisis__public=True) | Q(
            crisis__required_clue__discoveries__in=player.roster.discovered_clues)).distinct()


class StoryEmit(SharedMemoryModel):
    # chapter only used if we're not specifically attached to some episode
    chapter = models.ForeignKey('Chapter', blank=True, null=True,
                                on_delete=models.SET_NULL, related_name='emits')
    episode = models.ForeignKey('Episode', blank=True, null=True,
                                on_delete=models.SET_NULL, related_name='emits')
    text = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True,
                               on_delete=models.SET_NULL, related_name='emits')


class Milestone(SharedMemoryModel):
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

    def __str__(self):
        return "%s - %s" % (self.protagonist, self.name)


class Participant(SharedMemoryModel):
    milestone = models.ForeignKey('Milestone', on_delete=models.CASCADE)
    character = models.ForeignKey('RosterEntry', on_delete=models.CASCADE)
    xp_earned = models.PositiveSmallIntegerField(default=0, blank=0)
    karma_earned = models.PositiveSmallIntegerField(default=0, blank=0)
    gm_notes = models.TextField(blank=True, null=True)


class Comment(SharedMemoryModel):
    poster = models.ForeignKey('RosterEntry', related_name='comments')
    target = models.ForeignKey('RosterEntry', related_name='comments_upon', blank=True, null=True)
    text = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    gamedate = models.CharField(blank=True, null=True, max_length=80)
    reply_to = models.ForeignKey('self', blank=True, null=True)
    milestone = models.ForeignKey('Milestone', blank=True, null=True, related_name='comments')


class PlayerAccount(SharedMemoryModel):
    email = models.EmailField(unique=True)
    karma = models.PositiveSmallIntegerField(default=0, blank=0)
    gm_notes = models.TextField(blank=True, null=True)

    def __unicode__(self):
        return str(self.email)
    
    @property
    def total_xp(self):
        qs = self.accounthistory_set.all()
        return sum(ob.xp_earned for ob in qs)


class AccountHistory(SharedMemoryModel):
    account = models.ForeignKey('PlayerAccount', db_index=True)
    entry = models.ForeignKey('RosterEntry', db_index=True)
    xp_earned = models.SmallIntegerField(default=0, blank=0)
    gm_notes = models.TextField(blank=True, null=True)
    start_date = models.DateTimeField(blank=True, null=True, db_index=True)
    end_date = models.DateTimeField(blank=True, null=True, db_index=True)
    contacts = models.ManyToManyField('self', blank=True, through='FirstContact',
                                      related_name='contacted_by', symmetrical=False)

    def __str__(self):
        start = ""
        end = ""
        if self.start_date:
            start = self.start_date.strftime("%x")
        if self.end_date:
            end = self.end_date.strftime("%x")
        return "%s playing %s from %s to %s" % (self.account, self.entry, start, end)


class FirstContact(SharedMemoryModel):
    from_account = models.ForeignKey('AccountHistory', related_name='initiated_contacts', db_index=True)
    to_account = models.ForeignKey('AccountHistory', related_name='received_contacts', db_index=True)
    summary = models.TextField(blank=True)
    private = models.BooleanField(default=False)
    writer_share = models.BooleanField(default=False)
    receiver_share = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "First Impressions"

    def __str__(self):
        try:
            return "%s to %s" % (self.writer, self.receiver)
        except AttributeError:
            return "%s to %s" % (self.from_account, self.to_account)

    @property
    def writer(self):
        return self.from_account.entry

    @property
    def receiver(self):
        return self.to_account.entry

    @property
    def viewable_by_all(self):
        return self.writer_share and self.receiver_share


class RPScene(SharedMemoryModel):
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
        

class AbstractPlayerAllocations(SharedMemoryModel):
    UNSET_ROLL = -9999
    topic = models.CharField(blank=True, max_length=255, help_text="Keywords or tldr or title")
    actions = models.TextField(blank=True, help_text="The writeup the player submits of their actions, used for GMing.")
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
    action_points = models.PositiveSmallIntegerField(default=0, blank=0,
                                                     help_text="How many action points spent by player/assistants.")
    roll = models.SmallIntegerField(default=UNSET_ROLL, blank=True, help_text="Current dice roll")
    
    class Meta:
        abstract = True
        
    @property
    def roll_is_set(self):
        return self.roll != self.UNSET_ROLL
        
    
class Mystery(SharedMemoryModel):
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


class Revelation(SharedMemoryModel):
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


class Clue(SharedMemoryModel):
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
    allow_sharing = models.BooleanField(default=True, help_text="Can be shared")
    search_tags = models.ManyToManyField('SearchTag', blank=True, db_index=True)
    # if we were created for an RP event, such as a PRP
    event = models.ForeignKey("dominion.RPEvent", blank=True, null=True, related_name="clues")

    def __str__(self):
        return self.name

    @property
    def keywords(self):
        return [ob.name for ob in self.search_tags.all()]

    @property
    def creators(self):
        """
        Returns GMs of the event this clue was made for
        """
        if not self.event:
            return []
        try:
            return self.event.gms.all()
        except (AttributeError, IndexError):
            return []


class SearchTag(SharedMemoryModel):
    name = models.CharField(max_length=255, unique=True)
    topic = models.ForeignKey('LoreTopic', blank=True, null=True, db_index=True)

    def __str__(self):
        return self.name


class LoreTopic(SharedMemoryModel):
    name = models.CharField(max_length=255, unique=True)
    desc = models.TextField("GM Notes about this Lore Topic", blank=True)

    def __str__(self):
        return self.name


class MysteryDiscovery(SharedMemoryModel):
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


class RevelationDiscovery(SharedMemoryModel):
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


class RevelationForMystery(SharedMemoryModel):
    mystery = models.ForeignKey('Mystery', related_name="revelations_used", db_index=True)
    revelation = models.ForeignKey('Revelation', related_name="usage", db_index=True)
    required_for_mystery = models.BooleanField(default=True, help_text="Whether this must be discovered for the" +
                                                                       " mystery to finish")
    tier = models.PositiveSmallIntegerField(default=0, blank=0,
                                            help_text="How high in the hierarchy of discoveries this revelation is," +
                                                      " lower number discovered first")

    def __str__(self):
        return "Revelation %s used for %s" % (self.revelation, self.mystery)


class ClueDiscovery(SharedMemoryModel):
    clue = models.ForeignKey('Clue', related_name="discoveries", db_index=True)
    character = models.ForeignKey('RosterEntry', related_name="clues", db_index=True)
    investigation = models.ForeignKey('Investigation', blank=True, null=True, related_name="clues", db_index=True)
    message = models.TextField(blank=True, help_text="Message for the player's records about how they discovered this.")
    date = models.DateTimeField(blank=True, null=True)
    milestone = models.OneToOneField('Milestone', related_name="clue", blank=True, null=True)
    discovery_method = models.CharField(help_text="How this was discovered - exploration, trauma, etc",
                                        blank=True, max_length=255)
    roll = models.PositiveSmallIntegerField(default=0, blank=0, db_index=True)
    revealed_by = models.ForeignKey('RosterEntry', related_name="clues_spoiled", blank=True, null=True, db_index=True)

    class Meta:
        verbose_name_plural = "Clue Discoveries"

    @property
    def name(self):
        return self.clue.name

    @property
    def finished(self):
        return self.roll >= (self.clue.rating * DISCO_MULT)

    def display(self, show_sharing=False):
        if not self.finished:
            return self.message or "An investigation that hasn't yet yielded anything definite."
        msg = "\n{c%s{n\n" % self.clue.name
        msg += "{wRating:{n %s\n" % self.clue.rating
        msg += self.clue.desc + "\n"
        if self.message:
            msg += "\n" + self.message
        if show_sharing:
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
            return int((float(self.roll) / float(self.clue.rating * DISCO_MULT)) * 100)
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
            return False
        entry.investigations.filter(clue_target=self.clue).update(clue_target=None)
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
                MysteryDiscovery.objects.create(character=entry,
                                                message=message,
                                                mystery=mystery, date=datetime.now())
        pc.inform(msg, category="Investigations", append=False)
        return True

    @property
    def shared_with(self):
        spoiled = self.character.clues_spoiled.filter(clue=self.clue)
        return RosterEntry.objects.filter(clues__in=spoiled)


class ClueForRevelation(SharedMemoryModel):
    clue = models.ForeignKey('Clue', related_name="usage", db_index=True)
    revelation = models.ForeignKey('Revelation', related_name="clues_used", db_index=True)
    required_for_revelation = models.BooleanField(default=True, help_text="Whether this must be discovered for " +
                                                                          "the revelation to finish")
    tier = models.PositiveSmallIntegerField(default=0, blank=0,
                                            help_text="How high in the hierarchy of discoveries this clue is, " +
                                                      "lower number discovered first")

    def __str__(self):
        return "Clue %s used for %s" % (self.clue, self.revelation)


class InvestigationAssistant(SharedMemoryModel):
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

    @property
    def helper_name(self):
        name = self.char.key
        if hasattr(self.char, "owner"):
            name += " (%s)" % self.char.owner
        return name

    def shared_discovery(self, clue):
        self.currently_helping = False
        self.save()
        entry = self.roster_entry
        if entry:
            clue.share(entry)
        
    @property
    def roster_entry(self):
        """Gets roster entry object for either character or a retainer's owner"""
        try:
            return self.char.roster
        except AttributeError:
            # No roster entry, so we're a retainer. Try to return our owner's roster entry
            try:
                return self.char.owner.player.player.roster
            except AttributeError:
                pass


class Investigation(AbstractPlayerAllocations):
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

    def __str__(self):
        return "%s's investigation on %s" % (self.character, self.topic)

    def display(self):
        msg = "{wID{n: %s" % self.id
        if not self.active:
            msg += " {r(Investigation Not Currently Active){n"
        msg += "\n{wCharacter{n: %s\n" % self.character
        msg += "{wTopic{n: %s\n" % self.topic
        msg += "{wActions{n: %s\n" % self.actions
        msg += "{wModified Difficulty{n: %s\n" % self.difficulty
        msg += "{wCurrent Progress{n: %s\n" % self.progress_str
        msg += "{wStat used{n: %s\n" % self.stat_used
        msg += "{wSkill used{n: %s\n" % self.skill_used
        for assistant in self.active_assistants:
            msg += "{wAssistant:{n %s {wStat:{n %s {wSkill:{n %s {wActions:{n %s\n" % (
                assistant.helper_name, assistant.stat_used, assistant.skill_used, assistant.actions)
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
        msg += "{wAction Points Used{n: %s\n" % self.action_points
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
        stat = obj.stat_used or "wits"
        stat = stat.lower()
        skill = obj.skill_used or "investigation"
        skill = skill.lower()
        roll = do_dice_check(obj.char, stat_list=[stat, "perception", "intellect"], skill_list=[skill, "investigation"],
                             difficulty=diff, average_skill_list=True)
        return roll
    
    def do_roll(self, mod=0, diff=None):
        """
        Do a dice roll to return a result
        """
        diff = (diff if diff is not None else self.difficulty) + mod
        roll = self.do_obj_roll(self, diff)
        for ass in self.active_assistants:
            a_roll = self.do_obj_roll(ass, diff - 20)
            if a_roll < 0:
                a_roll = 0
            try:
                ability_level = ass.char.db.abilities['investigation_assistant']
            except (AttributeError, ValueError, KeyError, TypeError):
                ability_level = 0
            a_roll += random.randint(0, 5) * ability_level
            roll += a_roll
        try:
            roll = int(roll * settings.INVESTIGATION_PROGRESS_RATE)
        except (AttributeError, TypeError, ValueError):
            pass
        # save the character's roll
        print("final roll is %s" % roll)
        self.roll = roll
        self.save()
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
        mod += self.action_points/5
        return mod

    def get_roll(self):
        if self.roll == self.UNSET_ROLL:
            return self.do_roll()
        return self.roll
    #
    # def _set_roll(self, value):
    #     char = self.char
    #     char.db.investigation_roll = int(value)
    # roll = property(_get_roll, _set_roll)
    
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
        try:
            base = int(base + settings.INVESTIGATION_DIFFICULTY_MOD)
        except (AttributeError, ValueError, TypeError):
            pass
        return base - self.resource_mod

    @property
    def completion_value(self):
        if not self.targeted_clue:
            return 30
        return self.targeted_clue.rating * DISCO_MULT
    
    def check_success(self, modifier=0, diff=None):
        """
        Checks success. Modifier can be passed by a GM based on their
        discretion, but otherwise is 0. diff is passed if we don't
        want to find a targeted clue and generate our difficulty based
        on that.
        """
        roll = self.get_roll()
        if diff is not None:
            return (roll + self.progress) >= (diff + modifier)
        return (roll + self.progress) >= self.completion_value

    def process_events(self):
        self.generate_result()
        # reset values
        self.reset_values()
        self.char.attributes.remove("investigation_roll")
        # send along msg
        msg = "Your investigation into '%s' has had the following result:\n" % self.topic
        msg += self.results
        self.character.player.inform(msg, category="Investigations", append=False)

    def generate_result(self):
        """
        If we aren't GMing this, check success then set the results string
        accordingly.
        """
        if not self.automate_result:
            self.ongoing = False
            return
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
                roll = self.get_roll()
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
        
    def reset_values(self):
        """
        Reduce the silver/resources added to this investigation.
        """
        self.active = False
        self.silver = 0
        self.economic = 0
        self.military = 0
        self.social = 0
        self.action_points = 0
        self.roll = Investigation.UNSET_ROLL
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
        return get_keywords_from_topic(self.topic)

    def find_target_clue(self):
        """
        Finds a target clue based on our topic and our investigation history.
        We'll choose the lowest rating out of 3 random choices.
        """
        return get_random_clue(self.topic, self.character)

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
            return self.targeted_clue.rating * DISCO_MULT
        except (Clue.DoesNotExist, AttributeError):
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


class Theory(SharedMemoryModel):
    """
    Represents a theory that a player has come up with, and is now
    stored and can be shared with others.
    """
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="created_theories", blank=True, null=True,
                                db_index=True)
    known_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="known_theories", blank=True,
                                      through="TheoryPermissions")
    topic = models.CharField(max_length=255, blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    related_clues = models.ManyToManyField("Clue", related_name="theories", blank=True, db_index=True)
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

    def share_with(self, player):
        permission, _ = self.theory_permissions.get_or_create(player=player)

    def forget_by(self, player):
        permission = self.theory_permissions.filter(player=player)
        permission.delete()

    def add_editor(self, player):
        permission, _ = self.theory_permissions.get_or_create(player=player)
        permission.can_edit = True
        permission.save()

    def remove_editor(self, player):
        """
        Removes a player as an editor if they already were one.
        Args:
            player: Player to stop being an editor
        """
        # if they're not an editor, we don't create a theory_permission for them, since that would share theory
        try:
            permission = self.theory_permissions.get(player=player)
            permission.can_edit = False
            permission.save()
        except TheoryPermissions.DoesNotExist:
            pass

    @property
    def can_edit(self):
        return self.known_by.filter(theory_permissions__can_edit=True)


class TheoryPermissions(SharedMemoryModel):
    player = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="theory_permissions")
    theory = models.ForeignKey("Theory", related_name="theory_permissions")
    can_edit = models.BooleanField(default=False)


def get_keywords_from_topic(topic):
    old_topic = topic
    topic = topic.strip("?").strip(".").strip("!").strip(":").strip(",").strip(";")
    # convert to str from unicode
    k_words = [str(ob) for ob in topic.split()]
    # add singular version
    k_words.extend([ob[:-1] for ob in k_words if ob.endswith("s") and len(ob) > 1])
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
    if old_topic not in k_words:
        k_words.append(str(old_topic))
    return set(k_words)


def get_random_clue(topic, character):
    """
    Finds a target clue based on our topic and our investigation history.
    We'll choose the lowest rating out of 3 random choices.
    """
    exact = Clue.objects.filter(Q(allow_investigation=True) &
                                Q(search_tags__name__iexact=topic) &
                                ~Q(characters=character)).order_by('rating')
    if exact:
        return random.choice(exact)
    k_words = get_keywords_from_topic(topic)
    # build a case-insensitive query for each keyword of the investigation
    query = Q()
    for k_word in k_words:
        if not k_word:
            continue
        query |= Q(search_tags__name__iexact=k_word)
    # only certain clues - ones that can be investigated, exclude ones we've already started
    candidates = Clue.objects.filter(allow_investigation=True, search_tags__isnull=False).exclude(characters=character)
    # now match them by keyword
    candidates = candidates.filter(query).distinct()
    try:
        return random.choice(candidates)
    except (IndexError, TypeError):
        return None
