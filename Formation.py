from model.Move import Move
from model.ActionType import ActionType
from model.World import World
from model.Game import Game
from model.Player import Player
from Analyze import WorldState,  Vehicles
from Utils import Area,  get_center


class Formation:
  def __init__(self, groupnum: int):
    self.group = groupnum
    self.decision_list = []
  def select(self, m: Move):
    m.action = ActionType.CLEAR_AND_SELECT
    m.group = self.group
  def position(self, vehicles: Vehicles):
    return get_center(vehicles.resolve(self.units(vehicles)))
  def area(self, vehicles: Vehicles):
    return Area.from_units(vehicles.resolve(self.units(vehicles)))
  def units(self, vehicles: Vehicles):
    return vehicles.by_group[self.group]
  def tick(self, ws: WorldState, w: World, p: Player, g: Game, m: Move):
    resetflag = False
    for behavior in self.decision_list:
      if resetflag:
        behavior.reset()
      elif behavior.on_tick(ws,  w,  p,  g):
        allunits = self.units(ws.vehicles)
        allunitslen = len(allunits)
        is_selected = len(allunits & ws.vehicles.selected) == allunitslen
        if is_selected:
          behavior.act(ws, w, p, g, m)
        else:
          self.select(m)
        if m.action != ActionType.NONE:
          resetflag = True

from Behaviors import NuclearAlert,  Chase, KeepTogether, Nuke

class GroundFormation(Formation):
  def __init__(self,  groupnum: int):
    Formation.__init__(self, groupnum)
    self.decision_list = [
      NuclearAlert(self),
      KeepTogether(self),
      Nuke(self),
      Chase(self)
    ]

