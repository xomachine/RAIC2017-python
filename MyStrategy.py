from model.ActionType import ActionType
from model.Game import Game
from model.Move import Move
from model.Player import Player
from model.World import World
from model.FacilityType import FacilityType
from model.Unit import Unit
from model.VehicleType import VehicleType
from collections import deque
from math import pi

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
      (i.owner_player_id == self.me and self.allies or
       i.owner_player_id == self.opponent or self.neutral).add(i.id)


class WorldState:
  def __init__(self, world: World):
    self.vehicles = Vehicles(world)
    self.facilities = Facilities(world)

  def update(self, world: World):
    self.vehicles.update(world)
    self.facilities.update(world)

def get_square(vehicles: list):
  maxx = 0
  maxy = 0
  minx = 1000
  miny = minx
  for v in vehicles:
    if v.x < minx:
      minx = v.x
    if v.x > maxx:
      maxx = v.x
    if v.y < miny:
      miny = v.y
    if v.y > maxy:
      maxy = v.y
  return Area(minx, maxx, miny, maxy)

def wait(ticks: int, act):
  counter = ticks
  def do_wait(s: MyStrategy, w: World, m: Move):
    dest_index = w.tick_index + counter
    def captured(s: MyStrategy, w: World, m: Move):
      if w.tick_index >= dest_index:
        act(s, w, m)
        return False
      else:
        return True
    s.current_action.appendleft(captured)
  return do_wait

def rough_clasterize(points: list, thresh: float = 10, kgrid: int = 10):
  ## Rough clasterization algorithm. No idea if it works
  ## returns set of clusters. each cluster is set of point numbers in original
  ## list
  clusters = set()
  xs = dict()
  ys = dict()
  for p in range(0, len(points)-1):
    point = points[p]
    xpos = point.x // kgrid
    xs.setdefault(xpos, set()).add(p)
    ypos = point.y // kgrid
    ys.setdefault(ypos, set()).add(p)
  for p in range(0, len(points)-1):
    attached = False
    for c in clusters:
      if p in cc:
        attached = True
        break
    if not attached:
      point = points[p]
      xpos = point.x // kgrid
      ypos = point.y // kgrid
      newster = set([p])
      nears = ((xs[xpos] | xs[xpos+1] | xs[xpos-1]) &
               (ys[ypos] | ys[ypos+1] | ys[ypos-1])) ^ newster
      attach_to = set()
      for np in nears:
        npoint = points[np]
        distance_sq = (point.x - npoint.x)**2 + (point.y - npoint.y)**2 
        if distance_sq < thresh**2:
          ## We can also take all near points instead of checking distance
          ## if we want better performance
          attached = False
          for c in clusters:
            if np in c:
              attached = True
              attach_to.add(c)
              break
          if not attached:
            newster.add(np)
      for a in attach_to:
        newster |= a
        clusters.discard(a)
      clusters.add(newster)
  return clusters

def rotate(angle: float, center: Unit, max_speed: float = 0.0):
  def do_rotate(s: MyStrategy, w: World, m: Move):
    m.action = ActionType.ROTATE
    m.angle = angle
    m.max_angular_speed = max_speed
    m.x = center.x
    m.y = center.y
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

def shuffle(s, g: Game):
  vs = s.worldstate.vehicles
  myvs = vs.resolve(vs.by_player[vs.me])
  myarea = get_square(myvs)
  back = Unit(None, -1000.0, -1000.0)
  rot_dot = Unit(None, (myarea.left + myarea.right)/2,
                 (myarea.top + myarea.bottom)/2)
  return deque([
    select_vehicles(s.full_area),
    rotate(-pi, rot_dot),
    wait(200, move(back)),
    wait(100, rotate(pi, rot_dot)),
    wait(200, move(back)),
    wait(100, rotate(-pi/2, rot_dot)),
    wait(100, move(back)),
    wait(60, rotate(pi/4, rot_dot)),
    wait(60, move(back)),
  ])


def move_to_enemies(max_speed: float):
  def do_move(s: MyStrategy, w: World, m: Move):
    vs = s.worldstate.vehicles
    enemies = vs.resolve(vs.by_player[vs.opponent])
    earea = get_square(enemies)
    my = vs.resolve(vs.by_player[vs.me])
    marea = get_square(my)
    dx = (earea.left+earea.right)/2 - (marea.left+marea.right)/2
    dy = (earea.top+earea.bottom)/2 - (marea.top+marea.bottom)/2
    destination = Unit(None, dx, dy)
    mfunc = move(destination, max_speed = max_speed)
    mfunc(s, w, m)
  return do_move

class MyStrategy:
  current_action = deque()
  waiter = -1
  def init(self, me: Player, world: World, game: Game):
    self.full_area = Area(0.0,world.width,0.0,world.height)
    self.worldstate = WorldState(world)

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
      self.current_action = shuffle(self, game)
      self.current_action += shuffle(self, game)
    self.analyze(me, world, game)
    if world.tick_index % 1000 == 0 and world.tick_index > 2000:
      #self.current_action += [
      #  select_vehicles(self.full_area, group = 1),
      #  rotate(pi/4),
      #  select_vehicles(self.full_area, group = 2),
      #  rotate(pi/4),
      #  select_vehicles(self.full_area, group = 3),
      #  rotate(pi/4),
      #]
      self.current_action += [
        wait(100, move_to_enemies(game.tank_speed * game.forest_terrain_speed_factor))
      ]
    if len(self.current_action) > 0 and self.actionsRemaining > 0:
      act = self.current_action.popleft()
      if act(self, world, move):
        self.current_action.appendleft(act)
      else:
        self.actionsRemaining -= 1

