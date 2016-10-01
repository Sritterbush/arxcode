"""
Agents

So these will be npcs in game that can be controlled by
players. We're going with this design which is more MUD-like
than MUSH-like because we feel abstraction of political power
results in it simply being ignored in RP. If guards simply don't
do anything, then players will ignore them as being irrelevant,
resulting in politically powerful characters having no real power
in practice.

Agenthandler is created by each agent instance during its
__init__ and is populated with the instances of agents we find
in the world.
"""

from evennia.utils.create import create_object
from typeclasses.npcs import npc_types

npc_typeclass = "typeclasses.npcs.npc.Agent"
retainer_typeclass = "typeclasses.npcs.npc.Retainer"


class AgentHandler(object):
    def __init__(self, agent):
        self.agent = agent

    def get_type_name(self, tnum):
        return npc_types.get_npc_singular_name(tnum)

    def _get_unassigned(self):
        return self.agent.agent_objects.filter(quantity=0)
    unassigned = property(_get_unassigned)

    def find_agentob_by_character(self, character):
        for agent in self.agent.active:
            if agent.dbobj.db.guarding == character:
                return agent

    def get_or_create_agentob(self, num):
        assert (self.agent.quantity >= num), "Not enough agents to assign."
        if self.agent.unique:
            # ensure we can only ever have one agent object
            agent_obs = self.agent.agent_objects.all()
            if agent_obs:
                agent_ob = agent_obs[0]
            else:
                agent_ob = self.agent.agent_objects.create(quantity=1)
        else:
            if self.unassigned:
                agent_ob = self.unassigned[0]
                agent_ob.quantity = num
            else:
                agent_ob = self.agent.agent_objects.create(quantity=num)
        self.agent.quantity -= num
        self.agent.save()
        if not agent_ob.dbobj:
            if self.agent.unique:
                ntype = retainer_typeclass
            else:
                ntype = npc_typeclass
            ob = create_object(typeclass=ntype, key=self.agent.name or "Unnamed Agent")
            agent_ob.dbobj = ob
            agent_ob.save()
        agent_ob.dbobj.setup_agent()
        return agent_ob      

    def assign(self, targ, num):
        if not self.agent.unique:    
            agent_ob = self.find_agentob_by_character(targ)
            if agent_ob:
                self.agent.quantity -= num
                self.agent.save()
                agent_ob.reinforce(num)
                targ.msg("Your number of guards has been increased by %s." % num)
                return
        agent_ob = self.get_or_create_agentob(num)
        agent_ob.dbobj.assign(targ)
        agent_ob.save()
        targ.msg("%s %s been assigned to you." % (agent_ob.dbobj.name,
                                                  "has" if self.agent.unique else "have"))

    def room_summon(self, room, num=1):
        agent_ob = self.get_or_create_agentob(num)


