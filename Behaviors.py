from model.World import World
from model.Game import Game
from model.Move import Move
from model.Player import Player
from model.Unit import Unit
from model.ActionType import ActionType
from Formation import Formation
from Analyze import WorldState
from Utils import get_center, get_min_speed

class Behavior:
  def __init__(self, holder: Formation):
    self.holder = holder
    self.acting = False
  def reset(self):
    self.acting = False
  def on_tick(self, world: World, state: WorldState, player: Player, game: Game, move: Move):
    return False

class Repair(Behavior):
  def on_tick(self, ws: WorldState, world: World, player: Player, game: Game):
    pass

class NuclearAlert(Behavior):
  def on_tick(self, ws: WorldState, world: World, player: Player, game: Game):
    enemy = ws.opponent
    if enemy.next_nuclear_strike_tick_index > 0:
      holderarea = self.holder.area(ws.vehicles)
      if holderarea.is_inside(Unit(None,  enemy.next_nuclear_strike_x, enemy.next_nuclear_strike_y)):
        return True
    self.acting = False
    return False
  def act(self, ws: WorldState, w: World, p: Player, g: Game, m: Move):
    if self.acting:
      return
    m.action = ActionType.SCALE
    m.x = ws.opponent.next_nuclear_strike_x
    m.y = ws.opponent.next_nuclear_strike_y
    m.factor = 10
    self.acting = True

class Chase(Behavior):
  def __init__(self, holder: Formation, gridsize: int = 10):
    Behavior.__init__(self, holder)
    self.max_speed = 0
    self.gridsize = gridsize
    self.cellx = -1
    self.celly = -1
  def on_tick(self, ws: WorldState, world: World, player: Player, game: Game):
    if self.max_speed == 0:
      self.max_speed = get_min_speed(game, ws.vehicles, ws.vehicles.by_group[self.holder.group])
    return True
  def act(self, ws: WorldState, w: World, p: Player, g: Game, m: Move):
    formationcenter = get_center(ws.vehicles.resolve(self.holder.units(ws.vehicles)))
    minvalue = 10000
    for c in ws.vehicles.by_cluster(ws.vehicles.opponent):
      cluster = list(ws.vehicles.resolve(c))
      clustercenter = get_center(cluster)
      #clusterarea = Area.from_units(cluster)
      clusterdistance = clustercenter.get_distance_to_unit(formationcenter)
      #clusterangle = get_angle_between(clustercenter,  formationcenter)
      clustersize = len(cluster)
      value = clusterdistance/10 + clustersize
      if value < minvalue:
        destination = clustercenter
        minvalue = value
    if minvalue == 10000:
      print("Minimal cluster was not found")
      return
    cellx = destination.x // self.gridsize
    celly = destination.y // self.gridsize
    if self.cellx == cellx and self.celly == celly:
      return
    # TODO: simple pathfinding
    print("Setting action")
    m.action = ActionType.MOVE
    m.x = destination.x - formationcenter.x
    m.y = destination.y - formationcenter.y
    m.max_speed = self.max_speed
