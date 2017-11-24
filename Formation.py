from model.Move import Move
from model.ActionType import ActionType
from model.World import World
from model.Game import Game
from model.Player import Player
from model.Unit import Unit
from Analyze import WorldState,  Vehicles
from Utils import Area,  get_center


class Formation:
  def __init__(self, groupnum: int):
    self.group = groupnum
    self.delayed = None
    self.decision_list = []
    self.last_direction = None
  def select(self, m: Move):
    m.action = ActionType.CLEAR_AND_SELECT
    m.group = self.group
    #print("selected group ",  m.group)
  def position(self, vehicles: Vehicles):
    return get_center(vehicles.resolve(self.units(vehicles)))
  def area(self, vehicles: Vehicles):
    return Area.from_units(vehicles.resolve(self.units(vehicles)))
  def units(self, vehicles: Vehicles):
    return vehicles.by_group[self.group]
  def __str__(self):
    return "Formation of group " + str(self.group)
  def tick(self, ws: WorldState, w: World, p: Player, g: Game, m: Move):
    resetflag = False
    if self.delayed:
      m.action = self.delayed.action
      m.x = self.delayed.x
      m.y = self.delayed.y
      m.vehicle_id = self.delayed.vehicle_id
      m.angle = self.delayed.angle
      m.factor = self.delayed.factor
      m.max_speed = self.delayed.max_speed
      self.delayed = None
      if m.action == ActionType.MOVE:
        self.last_direction = Unit(None, m.x,  m.y)
      else:
        self.last_direction = None
      return
    for behavior in self.decision_list:
      if resetflag:
        behavior.reset()
      elif behavior.on_tick(ws,  w,  p,  g):
        allunits = self.units(ws.vehicles)
        allunitslen = len(allunits)
        selected_from_all =  len(allunits & ws.vehicles.selected)
        #print("selected:",  selected_from_all,  "\nall:",  allunitslen)
        is_selected = selected_from_all == allunitslen
        if is_selected:
          behavior.act(ws, w, p, g, m)
        else:
          self.delayed = Move()
          behavior.act(ws, w, p, g, self.delayed)
          if self.delayed.action and self.delayed.action != ActionType.NONE:
            self.select(m)
          else:
            self.delayed = None
#        if m.action and m.action != ActionType.NONE:
#          if m.action == ActionType.MOVE:
#            self.last_direction = Unit(None, m.x,  m.y)
#          else:
#            self.last_direction = None
#          print("Taken action " + str(m.action) + " by " + str(behavior) + " in " + str(self))
#        else:
#          print("Group ",  self.group,  " skipped action via ",  behavior)
        resetflag = True

from Behaviors import NuclearAlert,  Chase, KeepTogether, Nuke, Repair

class AerialFormation(Formation):
  def __init__(self, groupnum):
    Formation.__init__(self, groupnum)
    print("Made aerial formation for group ",  groupnum)
    self.decision_list = [
      NuclearAlert(self),
      Repair(self),
      KeepTogether(self),
      Nuke(self),
      Chase(self)
    ]

class GroundFormation(Formation):
  def __init__(self,  groupnum: int):
    print("Made ground formation for group ",  groupnum)
    Formation.__init__(self, groupnum)
    self.decision_list = [
      NuclearAlert(self),
      KeepTogether(self),
      Nuke(self),
      Chase(self)
    ]

