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
from functools import reduce

fuzz = 1
criticaldensity = 1/32 # how tight should the vehicles stay

class Area:
  def __init__(self, l: float, r: float, t: float, b: float):
    self.left = l
    self.top = t
    self.right = r
    self.bottom = b
  def copy(a):
    return Area(a.left, a.right, a.top, a.bottom)
  def area(self):
    return (self.right - self.left) * (self.bottom - self.top)
  def __str__(self):
    return str(self.left) + " <> " + str(self.right) + ":" + str(self.top) + "^V" + str(self.bottom)

class TaggedDict(dict):
  def __init__(self, data):
    dict.__init__(self)
    for i in data:
      self[i.id] = i

  def resolve(self, data: set):
    return map(lambda i: self[i], data)

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

  def in_area(self, a: Area):
    result = set()
    for k, v in self.items():
      if v.x >= a.left and v.x <= a.right and v.y >= a.top and v.y <= a.bottom:
        result.add(k)
    return result

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
  return Area(minx, maxx, miny, maxy)

def fill_flag(name: str):
  def do_fill(s: MyStrategy, w: World, m: Move):
    if name in s.flags:
      s.flags[name] += 1
    else:
      s.flags[name] = 1
  return do_fill

def at_flag(name: str, count: int, actions: deque):
  ## Adds actions to current queue if flag filled
  def event(s: MyStrategy, w: World, c: int = count):
    if (not (name in s.flags)) or s.flags[name] >= c:
      ## If dict key does not exist, it means that previous handler just
      ## have deleted it and flag had filled before
      s.current_action = actions + s.current_action
      if name in s.flags:
        s.flags.pop(name)
      return True
    return False
  def do_add_event(s: MyStrategy, w: World, m:Move):
    if not (name in s.flags):
      s.flags[name] = 0
    s.events.append(event)
  return do_add_event

def at_move_end(watchers: set, actions: deque):
  name = "move_end:" + str(hash(frozenset(watchers)))
  print(name)
  def do_eventme(s: MyStrategy, w: World):
    intersect = s.worldstate.vehicles.updated & watchers
    if len(intersect) == 0:
      s.flags[name] += 1
    else:
      s.flags[name] = 0
    if s.flags[name] >= 2:
      s.flags.pop(name)
      s.current_action = actions + s.current_action
      return True
    else:
      return False
  def do_waitme(s: MyStrategy, w: World, m:Move):
    s.events.append(do_eventme)
    s.flags[name] = 0
  return do_waitme

def wait(ticks: int):
  counter = ticks
  def do_wait(s: MyStrategy, w: World, m: Move):
    s.waiter = w.tick_index + counter
  return do_wait

def clusterize(ipoints: list, thresh: float = 10, kgrid: int = 10):
  ## Rough clasterization algorithm. No idea if it works
  ## returns set of clusters. each cluster is set of point numbers in original
  ## list
  clusters = set()
  xs = dict()
  ys = dict()
  points = list(ipoints)
  for p in range(len(points)):
    point = points[p]
    xpos = int(point.x // kgrid)
    xs.setdefault(xpos, set()).add(p)
    ypos = int(point.y // kgrid)
    ys.setdefault(ypos, set()).add(p)
  for p in range(len(points)):
    attached = False
    for c in clusters:
      if p in c:
        attached = True
        break
    if not attached:
      point = points[p]
      xpos = int(point.x // kgrid)
      ypos = int(point.y // kgrid)
      newster = set([p])
      def gset(a: dict, p:int):
        return a.get(p, set())
      nears = ((gset(xs, xpos) | gset(xs, xpos+1) | gset(xs, xpos-1) &
               (gset(ys, ypos) | gset(ys, ypos+1) | gset(ys, ypos-1)))
               ^ newster)
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
      clusters.add(frozenset(newster))
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
    m.left = a.left - fuzz
    m.right = a.right + fuzz
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
  eye_rad = 10
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
    fourth_turn = deque([
      #select_vehicles(ss.full_area),
      #rotate(-pi/2, Unit(None, central.right + fragment/2, mya.top + fragment*2))
      #hurricane,
      #hurricane,
      hurricane,
      fill_flag("formation_done"),
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
    halfparts = parts // 2
    therange = sorted(range(parts), key=lambda x: abs(x-halfparts))
    for i in therange:
      na = Area.copy(ss.full_area)
      na.top = step * i + mya.top
      na.bottom = step * (i+1) + mya.top
      vehicles = vss.in_area(na)
      print(na)
      print("Selected = " + str(len(vehicles)))
      ss.current_action.appendleft(at_move_end(vehicles, deque([fill_flag("loosed")])))
      ss.current_action.appendleft(move(Unit(None, 0, i*(2*step+4)-mya.top+10)))
      ss.current_action.appendleft(select_vehicles(na))
    ss.current_action.appendleft(at_flag("loosed", parts, second_turn))


  def act_it(desc: tuple, shift: float, waiter):
    ## enqueues actions to compactify the troops
    name = "first_maneur" + str(hash(frozenset(waiter)))
    second_turn = deque([
      select_vehicles(Area(shift, shift+desc[0].right-desc[0].left,
                           desc[0].top, desc[0].bottom), vtype = desc[1]),
      move(Unit(None, 0, 10+desc[0].bottom-2*desc[0].top)),
      at_move_end(desc[2], deque([fill_flag("compact")])),
    ])
    return deque([
      # horizontal adjust
      select_vehicles(desc[0], vtype = desc[1]),
      move(Unit(None, shift-desc[0].left, 0)),
      at_flag(name, len(waiter), second_turn),
      at_move_end(desc[2], deque([fill_flag(name)]))
    ])

  result = deque()
  gtypes = [VehicleType.ARRV, VehicleType.IFV, VehicleType.TANK]
  ftypes = [VehicleType.FIGHTER, VehicleType.HELICOPTER]
  grounds = map(prepare, gtypes)
  grounds = sorted(grounds, key=lambda x: x[0].left - 10*int(x[1] == VehicleType.TANK))
  flyers = map(prepare, ftypes)
  flyers = sorted(flyers, key=lambda x: x[0].left + x[0].top)
  mya = get_square(vs.resolve(flyies | groundies))
  shift = mya.left+2
  gap = 12 # just a little gap between vehicles to prevent stucking at collisions
  for g in grounds:
    result += act_it(g, shift, gtypes)
    shift += g[0].right - g[0].left + gap
  shift = mya.left+2
  for f in flyers:
    result += act_it(f, shift, ftypes)
    shift += f[0].right - f[0].left + gap
  myv = vs.resolve(pv)
  mya = get_square(myv)
  # 5 - is amount of vehicle types
  return result + deque([at_flag("compact", 5, deque([do_shuffle]))])

def move_to_enemies(max_speed: float):
  def do_move(s: MyStrategy, w: World, m: Move):
    vs = s.worldstate.vehicles
    enemies = list(vs.resolve(vs.by_player[vs.opponent]))
    clusters = clusterize(enemies)
    least = enemies
    value = 500
    for c in clusters:
      print("Cluster:" + str(len(c)))
      cluster = map(lambda x: enemies[x], c)
      new_value = map(lambda i: 1-int(i.type==0)-int(i.type==1)/2, cluster)
      new_value = reduce(lambda x, y: x+y, new_value)
      print(str(value) + " == " + str(new_value))
      if value > new_value:
        print(str(value) + " > " + str(new_value))
        least = cluster
        value = new_value
    earea = get_square(least)
    my = vs.resolve(vs.by_player[vs.me])
    marea = get_square(my)
    dx = (earea.left+earea.right)/2 - (marea.left+marea.right)/2
    dy = (earea.top+earea.bottom)/2 - (marea.top+marea.bottom)/2
    destination = Unit(None, dx, dy)
    s.current_action.appendleft(move(destination, max_speed = max_speed))
  return do_move

def hunt(game: Game):
  def do_hunt(s: MyStrategy, w: World, m: Move):
    vs = s.worldstate.vehicles
    myv = list(vs.resolve(vs.by_player[vs.me]))
    mya = get_square(myv)
    density = len(myv)/mya.area()
    print("Density is: " + str(density))
    print("Area is: " + str(mya))
    print("Amount is: " + str(len(myv)))
    if density < criticaldensity:
      s.current_action += deque([hurricane, hunt(game)])
    else:
      huntchain = deque([
        select_vehicles(s.full_area),
        move_to_enemies(game.tank_speed * game.swamp_terrain_speed_factor),
        wait(300),
        hunt(game)
      ])
      s.current_action += huntchain
  return do_hunt

class MyStrategy:
  current_action = deque()
  events = list()
  flags = dict()
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
      self.current_action += deque([
        at_flag("formation_done", 1, deque([hunt(game)]))
        ])
      self.current_action += shuffle(self)
    self.analyze(me, world, game)
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

