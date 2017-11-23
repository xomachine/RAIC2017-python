from model.World import World
from model.Game import Game
from model.Move import Move
from model.Player import Player
from model.Unit import Unit
from model.ActionType import ActionType
from model.VehicleType import VehicleType
from Formation import Formation
from Analyze import WorldState
from Utils import get_center, get_min_speed
from math import pi

class Behavior:
  def __init__(self, holder: Formation):
    self.holder = holder
    self.acting = False
  def reset(self):
    self.acting = False
  def on_tick(self, world: World, state: WorldState, player: Player, game: Game, move: Move):
    return False

class Nuke(Behavior):
  def on_tick(self, ws: WorldState, world: World, player: Player, game: Game):
    if player.remaining_nuclear_strike_cooldown_ticks > 0:
      self.acting = False
      return False
    formationcenter = get_center(ws.vehicles.resolve(self.holder.units(ws.vehicles)))
    mindistance = 2000
    for c in ws.vehicles.by_cluster(ws.vehicles.opponent):
      cluster = list(ws.vehicles.resolve(c))
      clustercenter = get_center(cluster)
      #clusterarea = Area.from_units(cluster)
      clusterdistance = clustercenter.get_distance_to_unit(formationcenter)
      if clusterdistance < mindistance:
        mindistance = clusterdistance
        self.target = clustercenter
    return mindistance < game.fighter_vision_range
  def act(self, ws: WorldState, w: World, p: Player, g: Game, m: Move):
    if self.acting:
      return
    nearest = -1
    mindistance = 2000
    for i in (self.holder.units(ws.vehicles) - ws.vehicles.damaged):
      distance = self.target.get_distance_to_unit(ws.vehicles[i])
      if distance < mindistance:
        mindistance = distance
        nearest = i
    if nearest < 0:
      return
    m.action = ActionType.TACTICAL_NUCLEAR_STRIKE
    m.x = self.target.x
    m.y = self.target.y
    m.vehicle_id = nearest

criticaldensity = 1/25

class KeepTogether(Behavior):
  def __init__(self, holder: Formation):
    Behavior.__init__(self, holder)
    self.current_action = ActionType.NONE
    self.currentactionticks = 0
    self.lastangle = pi
  def reset(self):
    self.current_action = ActionType.NONE
    self.currentactionticks = 0
  def on_tick(self, ws: WorldState, world: World, player: Player, game: Game):
    area = self.holder.area(ws.vehicles)
    amount = len(self.holder.units(ws.vehicles))
    density = amount / area.area()
    return density <= criticaldensity
  def act(self, ws: WorldState, w: World, p: Player, g: Game, m: Move):
    if self.currentactionticks > 50:
      self.currentactionticks = 0
      # change action
      target = self.holder.position(ws.vehicles)
      m.x = target.x
      m.y = target.y
      if self.current_action == ActionType.SCALE:
        m.action = ActionType.ROTATE
        self.lastangle *= -1
        m.angle = self.lastangle
        self.current_action = ActionType.ROTATE
      else:
        m.action = ActionType.SCALE
        m.factor = 0.1
        self.current_action = ActionType.SCALE
    else:
      self.currentactionticks += 1

class Repair(Behavior):
  def on_tick(self, ws: WorldState, world: World, player: Player, game: Game):
    self.gridsize = 10
    units = self.holder.units(ws)
    if len(ws.vehicles.damaged & units)/len(units) > 0.6:
      self.my_repairs = ws.vehicles.by_player[ws.vehicles.me] & ws.vehicles.by_type[VehicleType.ARRV]
      if len(self.my_repairs) == 0:
        return False
      return True

  def act(self, ws: WorldState, w: World, p: Player, g: Game, m: Move):
    repair_shops = ws.vehicles.clusterize(self.my_repairs)
    repair_shop_size = 0
    for r in repair_shops:
      rlen = len(r)
      if rlen > repair_shop_size:
        repair_shop_size = rlen
        target = r
    self.target_dot = get_center(ws.resolve(target))
    self.curpos = self.holder.position(ws.vehicles)
    if self.target_dot.x // self.gridsize != self.curpos.x // self.gridsize or self.target_dot.y // self.gridsize != self.curpos.y // self.gridsize:
      m.action = ActionType.MOVE
      m.x = self.target_dot.x - self.curpos.x
      m.y = self.target_dot.y - self.curpos.y

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
    m.action = ActionType.MOVE
    m.x = destination.x - formationcenter.x
    m.y = destination.y - formationcenter.y
    m.max_speed = self.max_speed
