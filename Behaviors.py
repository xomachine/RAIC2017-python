from model.World import World
from model.Game import Game
from model.Move import Move
from model.Player import Player
from model.Unit import Unit
from model.FacilityType import FacilityType
from model.ActionType import ActionType
from model.VehicleType import VehicleType
from Formation import Formation
from Analyze import WorldState
from Utils import get_center, get_min_speed, get_vision_range,  from_edge, is_loose
from deadcode import calculate
from math import pi

class Behavior:
  def __init__(self, holder: Formation):
    self.holder = holder
    self.acting = False
  def reset(self):
    self.acting = False
  def on_tick(self, world: World, state: WorldState, player: Player, game: Game, move: Move):
    return False

class Capture(Behavior):
  def on_tick(self, ws: WorldState, world: World, player: Player, game: Game):
    formationcenter = get_center(ws.vehicles.resolve(self.holder.units(ws.vehicles)))
    tol = 20
    if formationcenter.x < tol or formationcenter.x > world.width - tol or formationcenter.y < tol or formationcenter.y > world.height - tol:
      return True
    for c in ws.vehciles.by_cluster(ws.vehicles.me):
      cluster = list(ws.vehicles.resolve(c))
      clustercenter = get_center(cluster)
      #clusterarea = Area.from_units(cluster)
      clusterdistance = clustercenter.get_distance_to_unit(formationcenter)
      if clusterdistance < 100:
        self.needtogo = Unit(None,  formationcenter.x - clustercenter.x,  formationcenter.y - clustercenter.y)
        return True
    return False
  def act(self, ws: WorldState, w: World, p: Player, g: Game, m: Move):
    m.action = ActionType.MOVE

class Nuke(Behavior):
  def __init__(self, holder):
    Behavior.__init__(self, holder)
    self.stopped = False
  def on_tick(self, ws: WorldState, world: World, player: Player, game: Game):
    if player.next_nuclear_strike_vehicle_id in self.holder.units(ws.vehicles):
      self.acting = True
      return True
    if player.remaining_nuclear_strike_cooldown_ticks > 0 or NuclearAlert.on_tick(self, ws, world, player, game):
      self.acting = False
      return False
    #print("Nuke ready")
    formationcenter = get_center(ws.vehicles.resolve(self.holder.units(ws.vehicles)))
    mindistance = 2000
    for c in ws.vehicles.by_cluster(ws.vehicles.opponent):
      cluster = list(ws.vehicles.resolve(c))
      clustercenter = get_center(cluster)
      #clusterarea = Area.from_units(cluster)
      clusterdistance = clustercenter.get_distance_to_unit(formationcenter)
      if clusterdistance < mindistance and clusterdistance > game.tactical_nuclear_strike_radius * 0.9:
        mindistance = clusterdistance
        self.target = clustercenter
    if self.target is None or mindistance > game.fighter_vision_range:
      return False
    nearest = -1
    #mindistance = 2000
    for i in (self.holder.units(ws.vehicles)):
      distance = self.target.get_distance_to_unit(ws.vehicles[i])
      vis_range = get_vision_range(world, ws.vehicles[i],  game)
      if vis_range * 0.95 > distance and not i in ws.vehicles.damaged:
        nearest = i
        break
    if nearest < 0:
      print("Cannot find navigator")
      return False
    self.navigator = nearest
    return True

  def reset(self):
    Behavior.reset(self)
    self.stopped = False
    self.navigator = None

  def act(self, ws: WorldState, w: World, p: Player, g: Game, m: Move):
    if not self.stopped:
      m.action = ActionType.MOVE
      m.x = 0.1
      m.y = 0.1
      self.stopped = True
      return
    if self.acting:
      #print("Already nuking")
      return
    m.action = ActionType.TACTICAL_NUCLEAR_STRIKE
    m.x = self.target.x
    m.y = self.target.y
    m.vehicle_id = self.navigator
    self.acting = True

criticaldensity = 1/35

class KeepTogether(Behavior):
  def __init__(self, holder: Formation):
    Behavior.__init__(self, holder)
    self.current_action = ActionType.NONE
    self.currentactionticks = 0
    self.lastangle = pi
    self.maxticks = None
  def reset(self):
    self.current_action = ActionType.NONE
    self.currentactionticks = 0
  def on_tick(self, ws: WorldState, world: World, player: Player, game: Game):
    if self.maxticks is None:
      self.maxticks = 4/get_min_speed(game, ws.vehicles, self.holder.units(ws.vehicles))
    return is_loose(list(ws.vehicles.resolve(self.holder.units(ws.vehicles))))

  def act(self, ws: WorldState, w: World, p: Player, g: Game, m: Move):
    if self.currentactionticks <= 0:
      target = self.holder.position(ws.vehicles)
      self.currentactionticks = self.maxticks
      m.x = target.x
      m.y = target.y
      if self.current_action != ActionType.SCALE:
        m.action = ActionType.SCALE
        m.factor = 0.1
        self.current_action = ActionType.SCALE
      else:
        m.action = ActionType.ROTATE
        self.lastangle *= -1
        m.angle = self.lastangle
        self.current_action = ActionType.ROTATE
    elif self.current_action == ActionType.SCALE and not (self.holder.units(ws.vehicles) & ws.vehicles.updated):
      self.currentactionticks -= self.maxticks//2
    else:
      self.currentactionticks -= 1

class Repair(Behavior):
  def __init__(self, holder):
    Behavior.__init__(self, holder)
    self.cellx = -1
    self.celly = -1
  def on_tick(self, ws: WorldState, world: World, player: Player, game: Game):
    self.gridsize = 5
    units = self.holder.units(ws.vehicles)
    if len(ws.vehicles.damaged & units)/len(units) > 0.3:
      self.my_repairs = ws.vehicles.by_player[ws.vehicles.me] & ws.vehicles.by_type[VehicleType.ARRV]
      if len(self.my_repairs) == 0:
        return False
      repair_shops = ws.vehicles.clusterize(self.my_repairs)
      repair_shop_size = 0
      for r in repair_shops:
        rlen = len(r)
        if rlen > repair_shop_size:
          repair_shop_size = rlen
          target = r
      self.target_dot = get_center(ws.vehicles.resolve(target))
      self.curpos = self.holder.position(ws.vehicles)
      self.newcellx = self.target_dot.x // self.gridsize
      self.newcelly = self.target_dot.y // self.gridsize
      cellcx = self.curpos.x // self.gridsize
      cellcy = self.curpos.y // self.gridsize
      if self.newcellx == cellcx and self.newcelly == cellcy:
        return False
      return True

  def act(self, ws: WorldState, w: World, p: Player, g: Game, m: Move):
    if self.cellx == self.newcellx and self.celly == self.newcelly:
      return
    self.cellx = self.newcellx
    self.celly =self.newcelly
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
  def __init__(self, holder: Formation, gridsize: int = 5):
    Behavior.__init__(self, holder)
    self.max_speed = 0
    self.gridsize = gridsize
    self.cellx = -1
    self.celly = -1
    self.no_update = 0
  def on_tick(self, ws: WorldState, world: World, player: Player, game: Game):
    if self.max_speed == 0:
      self.max_speed = get_min_speed(game, ws.vehicles, ws.vehicles.by_group[self.holder.group])
    if not (self.holder.units(ws.vehicles) & ws.vehicles.updated):
      self.no_update += 1
    if self.no_update > 10:
      self.reset()
    return True

  def reset(self):
    Behavior.reset(self)
    self.no_update = 0
    self.cellx = -1
    self.celly = -1

  def act(self, ws: WorldState, w: World, p: Player, g: Game, m: Move):
    mine = ws.vehicles.resolve(self.holder.units(ws.vehicles))
    formationcenter = get_center(mine)
    maxvalue = 0
    if self.holder.ground:
      for f in (ws.facilities.by_player[ws.facilities.neutral] | ws.facilities.by_player[ws.facilities.opponent]):
        facility = ws.facilities[f]
        fcenter = Unit(None, facility.left+g.facility_width/2, facility.top + g.facility_height/2)
        distance = fcenter.get_squared_distance_to(formationcenter.x, formationcenter.y)
        if distance == 0:
          distance = 1
        value = 1500000/distance
        if value > maxvalue:
          maxvalue = value
          destination = fcenter
      #print("Selected facility as destination:",  maxvalue)
    for c in ws.vehicles.by_cluster(ws.vehicles.opponent):
      cluster = list(ws.vehicles.resolve(c))
      clustercenter = get_center(cluster)
      #clusterarea = Area.from_units(cluster)
      clusterdistance = clustercenter.get_squared_distance_to(formationcenter.x, formationcenter.y)
      #clusterangle = get_angle_between(clustercenter,  formationcenter)
      #clustersize = len(cluster)
      advantage = calculate(ws.effectiveness, ws.vehicles, g, self.holder.units(ws.vehicles), c, w.tick_index + self.holder.group*100000)
      if clusterdistance == 0:
        value = 0.000001
      else:
        value = (advantage + 1000 * int(p.remaining_nuclear_strike_cooldown_ticks == 0))**2/(clusterdistance)
      #value = clusterdistance/10 + clustersize - advantage
      #print("Cluster of size ",  clustersize, ", we have advantage ",  advantage,  ", so the value is ",  value)
      if value > maxvalue:
        destination = clustercenter
        maxvalue = value
        if clusterdistance < 100:
          break
    #print("Resultvalue:",  maxvalue)
    if maxvalue <=0:
      #print("Minimal cluster was not found")
      fromedge = from_edge(w, formationcenter)
      x = formationcenter.x - clustercenter.x + fromedge.x
      y = formationcenter.y - clustercenter.y + fromedge.y
      cellx = x//self.gridsize
      celly = y//self.gridsize
      if cellx != self.cellx or celly != self.celly:
        m.action = ActionType.MOVE
        m.x = x
        m.y = y
        m.max_speed = self.max_speed
        self.cellx = cellx
        self.celly = celly
      return
    cellx = destination.x // self.gridsize
    celly = destination.y // self.gridsize
    if self.cellx == cellx and self.celly == celly:
      #print("Skipped")
      return
    self.cellx = cellx
    self.celly = celly
    #direction = get_angle_between(destination, formationcenter)
    # TODO: simple pathfinding
    m.action = ActionType.MOVE
    m.x = destination.x - formationcenter.x
    m.y = destination.y - formationcenter.y
    m.max_speed = self.max_speed
