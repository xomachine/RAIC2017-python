from model.ActionType import ActionType
from model.Game import Game
from model.Move import Move
from model.Player import Player
from model.World import World
from model.FacilityType import FacilityType
from model.Unit import Unit
from model.VehicleType import VehicleType
from collections import deque

class Area:
  def __init__(self, l: float, r: float, t: float, b: float):
    self.left = l
    self.top = t
    self.right = r
    self.bottom = b
  def __str__(self):
    return str(self.left) + " <> " + str(self.right) + ":" + str(self.top) + "^V" + str(self.bottom)

class TaggedDict(dict):
  def __init__(self, data):
    dict.__init__(self)
    for i in data:
      self[i.id] = i

  def resolve(self, data: set):
    return [self[i] for i in data]

class Vehicles(TaggedDict):
  def __init__(self, world: World):
    self.me = world.get_my_player().id
    self.opponent = world.get_opponent_player().id
    self.by_player = dict()
    self.by_type = dict()
    TaggedDict.__init__(self, world.new_vehicles)
    for i in world.new_vehicles:
      self.by_player.setdefault(i.player_id, set()).add(i.id)
      self.by_type.setdefault(i.type, set()).add(i.id)

  def update(self, world: World):
    for i in world.new_vehicles:
      if not (i.id in self):
        self[i.id] = i
        self.by_player.setdefault(i.player_id, set()).add(i.id)
        self.by_type.setdefault(i.type, set()).add(i.id)
    for i in world.vehicle_updates:
      self[i.id].update(i)


class Facilities(TaggedDict):
  def __init__(self, world: World):
    self.allies = set()
    self.hostiles = set()
    self.neutral = set()
    self.by_type = dict()
    self.by_type[FacilityType.CONTROL_CENTER] = set()
    self.by_type[FacilityType.VEHICLE_FACTORY] = set()
    TaggedDict.__init__(self, world.facilities)
    self.me = world.get_my_player().id
    self.opponent = world.get_opponent_player().id
    for i in world.facilities:
      (i.owner_player_id == self.me and self.allies or
       i.owner_player_id == self.opponent or self.neutral).add(i.id)
      self.by_type[i.type].add(i.id)

  def update(self, world: World):
    self.allies.clear()
    self.hostiles.clear()
    self.neutral.clear()
    for i in world.facilities:
      (i.owner_player_id == self.me.id and self.allies or
       i.owner_player_id == self.opponent.id or self.neutral).add(i.id)


class WorldState:
  def __init__(self, world: World):
    self.vehicles = Vehicles(world)
    self.facilities = Facilities(world)

  def update(self, world: World):
    self.vehicles.update(world)
    self.facilities.update(world)

def rotate(angle: float, max_speed: float = 0.0):
  def do_rotate(s: MyStrategy, w: World, m: Move):
    m.action = ActionType.ROTATE
    m.angle = angle
    m.max_angular_speed = max_speed
  return do_rotate

def move(destination: Unit, max_speed: float = 0.0):
  def do_move(s: MyStrategy, w: World, m: Move):
    m.action = ActionType.MOVE
    m.x = destination.x
    m.y = destination.y
    m.max_speed = max_speed
  return do_move

def group(gnum: int, action: range(4, 6) = ActionType.ASSIGN):
  def do_group(s: MyStrategy, w: World, m: Move):
    m.action = action
    m.group = gnum
  return do_group

def select_vehicles(area: Area, vtype: VehicleType = None, group: int = 0,
                    action: range(1, 3) = ActionType.CLEAR_AND_SELECT):
  def do_select(s: MyStrategy, w: World, m: Move):
    m.action = action
    m.left = area.left
    m.right = area.right
    m.top = area.top
    m.bottom = area.bottom
    m.group = group
    m.vehicle_type = vtype
  return do_select

def make_initial_formation(ws, world: World):
  tanks = ws.vehicles.resolve(ws.vehicles.by_player[ws.vehicles.me] & ws.vehicles.by_type[VehicleType.TANK])
  print(len(tanks))
  tank_xs = [tank.x for tank in tanks]
  tank_ys = [tank.y for tank in tanks]
  halftanks = Area(min(tank_xs), max(tank_xs)/2, min(tank_ys), max(tank_ys))
  test_area = Area(0.0,world.width,0.0,world.height)
  print(halftanks)
  print(test_area)
  destination = Unit(None, world.width, world.height)
  return deque([
    select_vehicles(halftanks),
    move(destination),
  ])

class MyStrategy:
  def init(self, me: Player, world: World, game: Game):
    self.worldstate = WorldState(world)
    self.current_action = make_initial_formation(self.worldstate, world)

  def analyze(self, me: Player, world: World, game: Game):
    self.worldstate.update(world)
    facilities = self.worldstate.facilities
    myccid = facilities.by_type[FacilityType.CONTROL_CENTER] & facilities.allies
    self.actionsPerTick = (game.base_action_count +
      game.additional_action_count_per_control_center * len(myccid))
    if world.tick_index % 60 == 0:
      self.actionsRemaining = self.actionsPerTick

  def move(self, me: Player, world: World, game: Game, move: Move):
    if world.tick_index == 0:
      self.init(me, world, game)
    self.analyze(me, world, game)
    if len(self.current_action) > 0 and self.actionsRemaining > 0:
      act = self.current_action.popleft()
      self.actionsRemaining -= 1
      act(self, world, move)
