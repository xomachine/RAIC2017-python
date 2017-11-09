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
  def copy(a):
    return Area(a.left, a.right, a.top, a.bottom)
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
    self.updated = set()
    TaggedDict.__init__(self, world.new_vehicles)
    for i in world.new_vehicles:
      self.by_player.setdefault(i.player_id, set()).add(i.id)
      self.by_type.setdefault(i.type, set()).add(i.id)
      self.updated.add(i.id)

  def update(self, world: World):
    for i in world.new_vehicles:
      if not (i.id in self):
        self[i.id] = i
        self.by_player.setdefault(i.player_id, set()).add(i.id)
        self.by_type.setdefault(i.type, set()).add(i.id)
    self.updated = set()
    for i in world.vehicle_updates:
      if self[i.id].x != i.x or self[i.id].y != i.y:
        self.updated.add(i.id)
      self[i.id].update(i)
      if i.durability == 0:
        self.pop(i.id, None)
        for s in self.by_player.values():
          s.discard(i.id)
        for s in self.by_type.values():
          s.discard(i.id)


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
  return Area(minx - 6, maxx + 6, miny - 6, maxy + 6)

def at_move_end(watchers: set, actions: deque):
  nomoveturns = 0
  def do_eventme(s: MyStrategy, w: World):
    intersect = s.worldstate.vehicles.updated & watchers
    if len(intersect) == 0:
      s.nomoveturns += 1
    else:
      s.nomoveturns = 0
    if s.nomoveturns >= 2:
      print("Move over")
      s.current_action = actions + s.current_action
      return True
    else:
      return False
  def do_waitme(s: MyStrategy, w: World, m:Move):
    s.events.append(do_eventme)
    s.nomoveturns = 0
  return do_waitme

def wait(ticks: int):
  counter = ticks
  def do_wait(s: MyStrategy, w: World, m: Move):
    s.waiter = w.tick_index + counter
  return do_wait

def rough_clasterize(points: list, thresh: float = 10, kgrid: int = 10):
  ## Rough clasterization algorithm. No idea if it works
  ## returns set of clusters. each cluster is set of point numbers in original
  ## list
  clusters = set()
  xs = dict()
  ys = dict()
  for p in range(0, len(points)):
    point = points[p]
    xpos = point.x // kgrid
    xs.setdefault(xpos, set()).add(p)
    ypos = point.y // kgrid
    ys.setdefault(ypos, set()).add(p)
  for p in range(0, len(points)):
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

def group(gnum: int, action: range(4, 7) = ActionType.ASSIGN):
  def do_group(s: MyStrategy, w: World, m: Move):
    m.action = action
    m.group = gnum
  return do_group

def select_vehicles(area: Area, vtype: VehicleType = None, group: int = 0,
                    action: range(1, 4) = ActionType.CLEAR_AND_SELECT):
  def do_select(s: MyStrategy, w: World, m: Move, a = area):
    m.action = action
    print("Selecting: " + str(a))
    m.left = a.left
    m.right = a.right
    m.top = a.top
    m.bottom = a.bottom
    m.group = group
    m.vehicle_type = vtype
  return do_select

def hurricane(s, w:World, m: Move):
  vs = s.worldstate.vehicles
  pv = vs.by_player[vs.me]
  myv = vs.resolve(pv)
  mya = get_square(myv)
  print("Hurricane!")
  print(mya)
  epicenter = Unit(None, (mya.left + mya.right)/2, (mya.top + mya.bottom)/2)
  eye_rad = 30
  br = Unit(None, epicenter.x + eye_rad, epicenter.y + eye_rad)
  tr = Unit(None, epicenter.x + eye_rad, epicenter.y - eye_rad)
  bl = Unit(None, epicenter.x - eye_rad, epicenter.y + eye_rad)
  tl = Unit(None, epicenter.x - eye_rad, epicenter.y - eye_rad)
  cta = Area.copy(s.full_area)
  cta.bottom = tl.y
  cta.left = tl.x
  cra = Area.copy(s.full_area)
  cra.top = tr.y
  cra.left = tr.x
  cba = Area.copy(s.full_area)
  cba.top = br.y
  cba.right = br.x
  cla = Area.copy(s.full_area)
  cla.bottom = bl.y
  cla.right = bl.x
  ta = Area.copy(s.full_area)
  ta.bottom = tr.y
  ta.right = tr.x
  ra = Area.copy(s.full_area)
  ra.bottom = br.y
  ra.left = br.x
  ba = Area.copy(s.full_area)
  ba.top = bl.y
  ba.left = bl.x
  la = Area.copy(s.full_area)
  la.top = tl.y
  la.right = tl.x
  result = deque([
    select_vehicles(s.full_area),
    rotate(-pi/8, epicenter),
    wait(30),
    select_vehicles(ta),
    move(Unit(None, eye_rad, 2*eye_rad)),
    select_vehicles(ba),
    move(Unit(None, -eye_rad, -eye_rad*2)),
    select_vehicles(ra),
    move(Unit(None, -eye_rad*2, eye_rad)),
    select_vehicles(la),
    move(Unit(None, eye_rad*2, -eye_rad)),
    wait(150),
    select_vehicles(s.full_area),
    rotate(pi/4, epicenter),
    wait(30),
    select_vehicles(cta),
    move(Unit(None, -eye_rad, 2*eye_rad)),
    select_vehicles(cba),
    move(Unit(None, eye_rad, -eye_rad*2)),
    select_vehicles(cra),
    move(Unit(None, -eye_rad*2, -eye_rad)),
    select_vehicles(cla),
    move(Unit(None, eye_rad*2, eye_rad)),
    wait(150),
    select_vehicles(s.full_area),
    rotate(-pi/4, epicenter),
  ])
  s.current_action = result + s.current_action

def shuffle(s):
  vs = s.worldstate.vehicles
  pv = vs.by_player[vs.me]
  groundies = (vs.by_type[VehicleType.TANK] | vs.by_type[VehicleType.IFV] | vs.by_type[VehicleType.ARRV]) & pv
  flyies = (vs.by_type[VehicleType.FIGHTER] | vs.by_type[VehicleType.HELICOPTER]) & pv
  def prepare(t: VehicleType):
    vv = pv & vs.by_type[t]
    vehicles = vs.resolve(vv)
    varea = get_square(vehicles)
    return (varea, t, vv)
  def do_shuffle(ss: MyStrategy, w: World, m: Move):
    vss = ss.worldstate.vehicles
    myv = vss.resolve(pv)
    mya = get_square(myv)
    print("Area after alighment")
    print(mya)
    parts = 10
    step = (mya.bottom - mya.top) / parts
    central = Area.copy(ss.full_area)
    fragment = (mya.right - mya.left)/3
    central.left = mya.left + fragment
    central.right = mya.left + 2*fragment
    righter = Area.copy(ss.full_area)
    righter.left = central.right+2
    lefter = Area.copy(ss.full_area)
    lefter.right = central.left
    half = Area.copy(ss.full_area)
    half.left = mya.left + fragment/2
    fourth_turn = deque([
      #select_vehicles(ss.full_area),
      #rotate(-pi/2, Unit(None, central.right + fragment/2, mya.top + fragment*2))
      hurricane,
      hurricane,
      hurricane
    ])
    third_turn = deque([
      select_vehicles(lefter),
      move(Unit(None, central.left - lefter.left, 0)),
      select_vehicles(righter),
      move(Unit(None, central.left - righter.left, 0)),
      wait(50),
      at_move_end(pv, fourth_turn)
    ])
    second_turn = deque([
      select_vehicles(ss.full_area, vtype = VehicleType.FIGHTER),
      move(Unit(None, 0, step+1)),
      select_vehicles(ss.full_area, vtype = VehicleType.ARRV),
      move(Unit(None, 0, step+1)),
      select_vehicles(ss.full_area, vtype = VehicleType.IFV),
      move(Unit(None, 0, 2*step+3)),
      wait(50),
      at_move_end(pv, third_turn)
      ])
    ss.current_action.appendleft(at_move_end(pv, second_turn))
    halfparts = parts // 2
    therange = sorted([i for i in range(0, parts)], key=lambda x: abs(x-halfparts))
    for i in therange:
      na = Area.copy(ss.full_area)
      na.top = step * i + mya.top
      na.bottom = step * (i+1) + mya.top
      print(na)
      print(str(i*(2*step+3)-mya.top+10) +  " == " + str(i*(2*step+3)))
      ss.current_action.appendleft(move(Unit(None, 0, i*(2*step+4)-mya.top+10)))
      ss.current_action.appendleft(select_vehicles(na))


  def act_it(desc: tuple, shift: float, waiter):
    second_turn = deque([
      select_vehicles(Area(shift, shift+desc[0].right-desc[0].left,
                           desc[0].top, desc[0].bottom), vtype = desc[1]),
      move(Unit(None, 0, 10+desc[0].bottom-2*desc[0].top)),
    ])
    if desc[1] == VehicleType.TANK:
      second_turn += deque([at_move_end(pv, deque([do_shuffle]))])
    return deque([
      select_vehicles(desc[0], vtype = desc[1]),
      move(Unit(None, shift-desc[0].left, 0)),
      at_move_end(waiter, second_turn)
    ])

  result = deque()
  grounds = [prepare(i) for i in [VehicleType.ARRV, VehicleType.IFV, VehicleType.TANK]]
  grounds = sorted(grounds, key=lambda x: x[0].left - 10*int(x[1] == VehicleType.TANK))
  flyers = [prepare(i) for i in [VehicleType.FIGHTER, VehicleType.HELICOPTER]]
  flyers = sorted(flyers, key=lambda x: x[0].left + x[0].top)
  shift = 10
  for g in grounds:
    result += act_it(g, shift, g[2])
    shift += g[0].right - g[0].left + 5
  shift = 10
  for f in flyers:
    result += act_it(f, shift, f[2])
    shift += f[0].right - f[0].left + 5
  myv = vs.resolve(pv)
  mya = get_square(myv)
  return result

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
    s.current_action.appendleft(move(destination, max_speed = max_speed))
  return do_move

class MyStrategy:
  current_action = deque()
  events = list()
  waiter = -1
  nomoveturns = 0
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
      self.current_action = shuffle(self)
    self.analyze(me, world, game)
    if world.tick_index % 1000 == 0 and world.tick_index > 2000:
      self.current_action += [
        hurricane,
        select_vehicles(self.full_area),
        move_to_enemies(game.tank_speed * game.swamp_terrain_speed_factor),
      ]
    if len(self.current_action) > 0 and self.actionsRemaining > 0 and self.waiter < world.tick_index:
      act = self.current_action.popleft()
      print(act)
      if act(self, world, move):
        self.current_action.appendleft(act)
      if move.action != ActionType.NONE:
        self.actionsRemaining -= 1
    elif self.actionsRemaining > 0:
      to_remove = list()
      for i in reversed(self.events):
        if i(self, world):
          to_remove.append(i)
      for i in to_remove:
        self.events.remove(i)

