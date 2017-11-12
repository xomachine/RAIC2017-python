from model.ActionType import ActionType
from model.Game import Game
from model.Move import Move
from model.Player import Player
from model.World import World
from model.FacilityType import FacilityType
from model.Unit import Unit
from model.VehicleType import VehicleType
from collections import deque
from math import pi, copysign
from functools import reduce

fuzz = 1
criticaldensity = 1/25 # how tight should the vehicles stay
FLYERS = 0
GROUNDERS = 1
typebyname = {
  VehicleType.ARRV: "arrv",
  VehicleType.FIGHTER: "fighter",
  VehicleType.HELICOPTER: "helicopter",
  VehicleType.IFV: "ifv",
  VehicleType.TANK: "tank",
}
movables = [VehicleType.IFV, VehicleType.ARRV, VehicleType.FIGHTER]
types = [[VehicleType.HELICOPTER, VehicleType.FIGHTER],
         [VehicleType.TANK, VehicleType.IFV, VehicleType.ARRV]]

class Area:
  def __init__(self, l: float, r: float, t: float, b: float):
    self.left = l
    self.top = t
    self.right = r
    self.bottom = b
  def get_center(self):
    return Unit(None, (self.left + self.right)/2, (self.top + self.bottom)/2)
  def copy(a):
    return Area(a.left, a.right, a.top, a.bottom)
  def is_inside(self, point):
    return (point.x <= self.right and point.x >= self.left and
            point.y >= self.top and point.y <= self.bottom)
  def area(self):
    width = (self.right - self.left)
    height = (self.bottom - self.top)
    return  width * height + abs(width - height)**2
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
    self.by_group = dict()
    self.updated = set()
    self.damaged = set()
    TaggedDict.__init__(self, world.new_vehicles)
    for i in world.new_vehicles:
      self.by_player.setdefault(i.player_id, set()).add(i.id)
      self.by_type.setdefault(i.type, set()).add(i.id)
      self.updated.add(i.id)

  def in_area(self, a: Area):
    result = set()
    for k, v in self.items():
      if a.is_inside(v):
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
      health = i.durability / self[i.id].max_durability
      if i.id in self.by_player[self.me]:
        newgroups = set(i.groups)
        fullgroups = set(self.by_group)
        for g in i.groups:
          self.by_group.setdefault(g, set()).add(i.id)
        for g in fullgroups - newgroups:
          self.by_group[g].discard(i.id)
      if i.durability == 0:
        self.pop(i.id, None)
        for s in self.by_player.values():
          s.discard(i.id)
        for s in self.by_type.values():
          s.discard(i.id)
        for s in self.by_group.values():
          s.discard(i.id)
      elif health < 0.6:
        self.damaged.add(i.id)
      elif health > 0.99:
        self.damaged.discard(i.id)


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
       i.owner_player_id == self.opponent and self.hostiles or
       self.neutral).add(i.id)
      self.by_type[i.type].add(i.id)

  def update(self, world: World):
    self.allies.clear()
    self.hostiles.clear()
    self.neutral.clear()
    for i in world.facilities:
      (i.owner_player_id == self.me and self.allies or
       i.owner_player_id == self.opponent and self.hostiles or
       self.neutral).add(i.id)


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
    print("Filling flag: " + name)
    if name in s.flags:
      s.flags[name] += 1
    else:
      s.flags[name] = 1
  return do_fill

def at_flag(name: str, count: int, actions: deque):
  ## Adds actions to current queue if flag filled
  def event(s: MyStrategy, w: World, c: int = count):
    if (not (name in s.flags)) or s.flags[name] >= c:
      print("Got " + str(c) + " in " + name)
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
    print("Waiting " + str(count) + " on flag: " + name)
    s.events.append(event)
  return do_add_event

def at_move_end(watchers: set, actions: deque):
  name = "move_end:" + str(hash(frozenset(watchers)))
  def do_eventme(s: MyStrategy, w: World):
    intersect = s.worldstate.vehicles.updated & watchers
    if (not (name in s.flags)) or s.flags[name] >= 2:
      print("Move ended for " + name)
      if name in s.flags:
        s.flags.pop(name)
      s.current_action = actions + s.current_action
      return True
    if len(intersect) == 0:
      s.flags[name] += 1
    else:
      s.flags[name] = 0
    return False
  def do_waitme(s: MyStrategy, w: World, m:Move):
    s.events.append(do_eventme)
    print("Waiting move end for set:" + name)
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
    print("Moving to: " + str(destination.x) + ":" + str(destination.y))
    m.max_speed = max_speed
  return do_move

def group(gnum: int, action: range(4, 7) = ActionType.ASSIGN):
  def do_group(s: MyStrategy, w: World, m: Move):
    m.action = action
    m.group = gnum
    if action == ActionType.ASSIGN:
      s.free_groups.discard(gnum)
    elif action == ActionType.DISBAND:
      s.free_groups.add(gnum)
  return do_group

def scale(center: Unit, factor: float):
  def do_scale(s: MyStrategy, w: World, m: Move):
    m.action = ActionType.SCALE
    m.factor = factor
    m.x = center.x
    m.y = center.y
  return do_scale

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

def hurricane(group: int):
  def do_hurricane(s, w:World, m: Move):
    vs = s.worldstate.vehicles
    pv = vs.by_group[group]
    myv = vs.resolve(pv)
    mya = get_square(myv)
    print("Hurricane!")
    print(mya)
    epicenter = mya.get_center()
    result = deque([
      select_vehicles(s.full_area, group = group),
      scale(epicenter, 0.1),
      wait(30),
      select_vehicles(s.full_area, group = group),
      rotate(pi/2, epicenter),
      wait(30),
      select_vehicles(s.full_area, group = group),
      scale(epicenter, 0.1),
      wait(150),
      select_vehicles(s.full_area, group = group),
      rotate(-pi/4, epicenter),
      wait(30),
      select_vehicles(s.full_area, group = group),
      scale(epicenter, 0.1),
      wait(150),
      select_vehicles(s.full_area, group = group),
      rotate(pi/8, epicenter),
      wait(40),
      select_vehicles(s.full_area, group = group),
      scale(epicenter, 0.1),
    ])
    s.current_action = result + s.current_action
  return do_hurricane

def devide(unitset: set, each: callable, parts: int, name: str):
  ## devide unitset to `parts` parts and do `each` with each part
  ## each must be a callable that returns deque of actual actions and gets
  ## a group number as argument. actions will be applied in order from
  ## central part to edges
  ## the last argument is an event name which will be fired
  ## when devision is done. (at_flag)
  halfparts = parts // 2
  ordered = sorted(range(parts), key = lambda x: abs(x-halfparts))
  tmpname = "devision:" + str(hash(frozenset(unitset)))
  def do_devide(s: MyStrategy, w: World, m: Move):
    vs = s.worldstate.vehicles
    # to avoid non existing units we using intersection with
    # all players units
    pv = (vs.by_player[vs.me] & unitset)
    units = vs.resolve(pv)
    uarea = get_square(units)
    step = (uarea.bottom - uarea.top) / parts
    for i in ordered:
      pa = Area.copy(s.full_area)
      pa.top = step * i + uarea.top
      pa.bottom = step * (i+1) + uarea.top
      vehicles = vs.in_area(pa)
      s.current_action = (do_and_check(each(i, pa, uarea), tmpname, vehicles)
                          + s.current_action)
    s.current_action.appendleft(at_flag(tmpname, parts,
                                         deque([fill_flag(name)])))
  return do_devide

def select_types(types: list, area: Area):
  # Makes the queue of actions to select types list in given area
  action = ActionType.CLEAR_AND_SELECT
  result = []
  for t in types:
    result += [
      select_vehicles(area, vtype = t, action = action)
    ]
    action = ActionType.ADD_TO_SELECTION
  return deque(result)

def do_and_check(action, flag: str, group: set):
  ## Returns a sequence of actions to perform an action and check the flag
  ## after its end (the action end equals groups quiting moving)
  result = []
  if callable(action):
    result = deque([action])
  else:
    result = deque(action)
  return result + deque([
    wait(10),
    at_move_end(group, deque([fill_flag(flag)]))
  ])

def tight(group: set):
  ## Tights the group
  name = "devided:" + str(hash(frozenset(group)))
  def do_tight(s: MyStrategy, w: World, m: Move):
    vs = s.worldstate.vehicles
    pv = vs.by_player[vs.me]
    actualgroup = group & pv
    def each(i, partarea, fullarea):
      target = Unit(None, 0, (1 - 2 * i) * 1000)
      center = fullarea.get_center()
      return deque([
        #select_vehicles(partarea),
        #move(target),
        #wait(50),
        select_vehicles(partarea),
        scale(center, 0.1),
      ])
    s.current_action.appendleft(devide(actualgroup, each, 2, name))
  return do_tight

def initial_shuffle():
  ## Shuffles initially spawned groups of units into one
  ## Units should be initially set in one line
  ## Returns a closure to place into MyStrategy.current_action
  tightflag = "tighted"
  def do_shuffle(s: MyStrategy, w: World, m: Move):
    vs = s.worldstate.vehicles
    classes = [reduce(lambda x,y: y | x, list(map(lambda x: vs.by_type[x], i)))
               for i in types]
    pv = vs.by_player[vs.me]
    allunits = vs.resolve(pv)
    fullarea = get_square(allunits)
    pointofscale = Unit(None, fullarea.left, fullarea.top)
    result = deque()
    for clas in range(len(classes)):
      units = vs.resolve(classes[clas] & pv)
      area = get_square(units)
      pointofscale = Unit(None, area.left, area.top)
      spreadflag = "spread:" + str(clas)
      shiftflag = "shifted:" + str(clas)
      mergeflag = "merged:" + str(clas)
      spread_groups = select_types(types[clas], s.full_area)
      spread_groups += do_and_check(scale(pointofscale, len(types[clas])),
                                    spreadflag, classes[clas])
      shift_groups = deque()
      merge_groups = deque()
      slowpockarea = get_square(vs.resolve(vs.by_type[types[clas][0]]))
      for i in range(1, len(types[clas])):
        shift = 4 * i/len(types[clas]) # 4 - vehicle diameter
        thetype = types[clas][i]
        destination = Unit(None, 0, shift)
        group_of_interest = vs.by_type[thetype] & pv
        goi_area = get_square(vs.resolve(group_of_interest))
        shift_groups += deque([select_vehicles(s.full_area, vtype=thetype)])
        shift_groups += do_and_check(move(destination), shiftflag,
                                     group_of_interest)
        aligned_destination = Unit(None, slowpockarea.left - goi_area.left, 0)
        merge_groups += deque([select_vehicles(s.full_area, vtype = thetype)])
        merge_groups += do_and_check(move(aligned_destination), mergeflag, group_of_interest)
      tight_groups = select_types(types[clas], s.full_area)
      tight_groups += do_and_check(scale(pointofscale, 0.1), tightflag,
                                   classes[clas])
      result += shift_groups
      result += deque([at_flag(spreadflag, 1, merge_groups)])
      result += deque([at_flag(shiftflag, 1, spread_groups)])
      result += deque([at_flag(mergeflag, 1, tight_groups)])
      result += deque([at_flag(tightflag, 2, deque([fill_flag("shuffled")]))])
    s.current_action = result + s.current_action
  return do_shuffle

def do_shuffle(ss, w: World, m: Move):
  vss = ss.worldstate.vehicles
  pv = vss.by_player[vss.me]
  myv = vss.resolve(pv)
  mya = get_square(myv)
  print("Area after alighment")
  print(mya)
  parts = 10
  step = (mya.bottom - mya.top) / parts
  central = Area.copy(ss.full_area)
  fragment_area = get_square(vss.resolve(pv & vss.by_type[VehicleType.IFV]))
  fragment = fragment_area.right - fragment_area.left
  central.left = (mya.left + mya.right - fragment)/2
  central.right = central.left + fragment
  righter = Area.copy(ss.full_area)
  righter.right = mya.right
  righter.left = mya.right - fragment
  lefter = Area.copy(ss.full_area)
  lefter.left = mya.left
  lefter.right = mya.left + fragment
  #fourth_turn = deque([
    #select_vehicles(ss.full_area),
    #rotate(-pi/2, Unit(None, central.right + fragment/2, mya.top + fragment*2))
  def halfrotate(i, a, f):
    if i == 0:
      return deque()
    else:
      rcenter = f.get_center()
      rcenter.x = f.left - 2 # minus unit radius
      rcenter.y += 2 # plus unit radius
      return deque([select_vehicles(a), rotate(pi, rcenter)])
  fifth_turn = deque([
    at_flag("rerotated", 1, deque([fill_flag("formation_done")])),
    devide(vss.by_group[1], halfrotate, 2, "rerotated")
   ])
  fourth_turn = (do_and_check(tight(pv), "tighted", pv) +
    deque([at_flag("tighted", 1, fifth_turn)]))
  third_turn = deque([
    select_vehicles(lefter),
    move(Unit(None, central.left - lefter.left, 0)),
    select_vehicles(righter),
    move(Unit(None, central.left - righter.left, 0)),
    wait(10),
    at_move_end(pv, fourth_turn)
  ])
  second_turn = deque([
    select_vehicles(ss.full_area, vtype = VehicleType.FIGHTER),
    move(Unit(None, 0, step+1)),
    select_vehicles(ss.full_area, vtype = VehicleType.ARRV),
    move(Unit(None, 0, step+1)),
    select_vehicles(ss.full_area, vtype = VehicleType.IFV),
    move(Unit(None, 0, 2*step+3)),
    wait(10),
    at_move_end(pv, third_turn)
    ])
  def each(i, a, f):
    step = a.bottom - a.top
    center = f.get_center().y
    distributed_size = parts*(3*step+4)
    top_from_bottom = ss.full_area.bottom - distributed_size
    top_from_center = center - distributed_size/2
    top = (top_from_center < 0 and f.top + 10 or
           top_from_bottom < top_from_center and top_from_bottom or
           top_from_center)
    target = Unit(None, 0, i*(2*step+4)-top)
    return deque([
      select_vehicles(a),
      move(target),
      ])
  ss.current_action.appendleft(devide(pv, each, parts, "loosed"))
  ss.current_action.appendleft(at_flag("loosed", 1, second_turn))

def initial_compact(s):
  ## Compactifies the initial spawn into one line
  ## At the end of process will set the "compacted" flag
  ## Returns deque with actions. s - MyStrategy
  result = deque()
  vs = s.worldstate.vehicles
  pv = vs.by_player[vs.me]
  # hardcoded, no way to obtain dynamicaly
  spawnarea = Area(18, 220, 18, 220)
  squadarea = get_square(vs.resolve(vs.by_type[VehicleType.IFV] & pv))
  spawnarea_width = (spawnarea.right - spawnarea.left)
  colwidth = squadarea.right - squadarea.left
  centralleft = spawnarea.left + (spawnarea_width - colwidth) / 2
  centralright = centralleft + colwidth
  linewidth = squadarea.bottom - squadarea.top
  lines = [
    Area(spawnarea.left, spawnarea.right, spawnarea.top,
         spawnarea.top + linewidth),
    Area(spawnarea.left, spawnarea.right, centralleft, centralright),
    Area(spawnarea.left, spawnarea.right, spawnarea.bottom - linewidth,
         spawnarea.bottom),
  ]
  columns = [
    Area(spawnarea.left, spawnarea.left + colwidth, spawnarea.top,
         spawnarea.bottom),
    Area(centralleft, centralright, spawnarea.top, spawnarea.bottom),
    Area(spawnarea.right - colwidth, spawnarea.right, spawnarea.top,
         spawnarea.bottom),
  ]
  sets = [reduce(lambda x, y: y | x, list(map(lambda x: vs.by_type[x], i)))
          for i in types]
  namefull = "secondturn"
  def adjust(clas):
    ## Perform a vertical move
    secondturn = deque()
    name = namefull + ":" + str(clas)
    counted = 0
    for i in [0, 2]: # lines except central
      line = lines[i]
      target = Unit(None, 0, lines[1].top - line.top)
      for tt in types[clas]:
        squadtomove = vs.in_area(line) & vs.by_type[tt]
        if len(squadtomove) > 0:
          secondturn += do_and_check([select_vehicles(s.full_area, vtype = tt),
                                      move(target)], name, squadtomove)
          counted += 1
    return (deque([at_flag(name, counted, deque([fill_flag(namefull)]))]) +
            secondturn)
  for t in [FLYERS, GROUNDERS]:
    empties = set(range(3))
    registredflags = 0
    unitsfromset = [None]*len(columns)
    squadsfromset = [None]*len(columns)
    for i, col in enumerate(columns):
      colunits = vs.in_area(col)
      unitsfromset[i] = colunits & sets[t]
      squadsfromset[i] = len(unitsfromset[i])//100
      if squadsfromset[i] > 0:
        empties.discard(i)
    print("Type " + str(t) + " has " + str(squadsfromset) + " squads by columns")
    print(empties)
    for i, col in enumerate(columns):
      if squadsfromset[i] > 0:
        name = "firstturn:" + str(t)
        for tomovetype in movables:
          if squadsfromset[i] <= 1:
            break
          movecandidateset = (unitsfromset[i] & vs.by_type[tomovetype])
          if len(movecandidateset) == 0:
            continue
          if t == GROUNDERS and i != 1:
            sample = vs[movecandidateset.pop()]
            obstacle = set()
            print("Checking for obstacles...")
            for lno, line in enumerate(lines):
              if line.is_inside(sample):
                print("... at line " + str(lno))
                obstacle = (vs.in_area(line) & vs.in_area(columns[1]) &
                            sets[t])
                break
            if len(obstacle) > 0:
              print("Obstacle detected")
              obstacletype = vs[obstacle.pop()].type
              if obstacletype == VehicleType.TANK:
                print("It is tank, lets find something else to move")
                continue
              else:
                tcol = empties.pop()
                empties.add(1)
                target = Unit(None, columns[tcol].left - columns[1].left, 0)
                print("Move obstacle from 1 to " + str(tcol))
                result += do_and_check([
                  select_vehicles(s.full_area, vtype = obstacletype),
                  move(target)], name, unitsfromset[i])
                registredflags += 1
          tcol = empties.pop()
          target = Unit(None, columns[tcol].left - columns[i].left, 0)
          print("Move from " + str(i) + " to " + str(tcol))
          result += do_and_check([
            select_vehicles(s.full_area, vtype = tomovetype),
            move(target)], name, unitsfromset[i])
          registredflags += 1
          squadsfromset[i] -= 1
    result = deque([at_flag("firstturn:"+str(t), registredflags,
                            adjust(t))]) + result
  return deque([at_flag(namefull, 2, deque([fill_flag("compacted")]))]) + result

def shuffle(s):
  return (deque([at_flag("compacted", 1, deque([do_shuffle]))]) +
          initial_compact(s))

def move_to_enemies(gr: int, max_speed: float):
  valdst = 1 # amount over distance factor
  def do_move(s: MyStrategy, w: World, m: Move, max_speed = max_speed):
    vs = s.worldstate.vehicles
    aviaspeedfactor = 1
    myg = vs.by_group[gr]
    my = vs.resolve(myg)
    marea = get_square(my)
    mycenter = marea.get_center()
    aviasupport = vs.by_group[gr+1]
    enemies = list(vs.resolve(vs.by_player[vs.opponent]))
    clusters = clusterize(enemies)
    least = get_square(enemies)
    value = 500
    mindistance = 2000
    for c in clusters:
      print("Cluster:" + str(len(c)))
      cluster = list(map(lambda x: enemies[x], c))
      carea = get_square(cluster)
      clustercenter = carea.get_center()
      distance = mycenter.get_distance_to_unit(clustercenter)
      #new_value = map(lambda i: 1-int(i.type==0)-int(i.type==1)/2, cluster)
      #new_value = reduce(lambda x, y: x+y, new_value)
      new_value = len(cluster)
      criticaldistance = (new_value + len(myg))/4 # should be obtained empirically
      #print(str(value) + " == " + str(new_value))
      if distance < criticaldistance:
        # combat mode! fight or flee!
        cluset = set(cluster)
        if len((myg | aviasupport)-vs.damaged) - len(cluset-vs.damaged) > -1:
          #fight!
          print("Fight!")
          least = Unit(None, (clustercenter.x+mycenter.x)/2,
                       (clustercenter.y+mycenter.y)/2)
          max_speed = max_speed / 2
          aerialCount = len(aviasupport - vs.damaged)
          if aerialCount == 0:
            break
          aerialDangers = (vs.by_type[VehicleType.FIGHTER] |
                             vs.by_type[VehicleType.IFV])
          ifvCount = (len(cluset & aerialDangers) +
                      len(cluset & vs.by_type[VehicleType.TANK]) *
                      len(vs.by_type[VehicleType.HELICOPTER] & aviasupport)
                      / len(aviasupport))
          aviaadvantage = (aerialCount-ifvCount)/(ifvCount+aerialCount)
          if aviaadvantage > 0.3:
            # If avia advantage
            aviaspeedfactor = 2 + aviaadvantage
          elif len(aviasupport & myg) > 0:
            aviaspeedfactor = 0.5
        else:
          print("Flee!")
          least = Unit(None, 2*mycenter.x-clustercenter.x, 2*mycenter.y-clustercenter.y)
          #flee!
        break
      if value * valdst + mindistance > new_value * valdst + distance:
        #print(str(value) + " > " + str(new_value))
        least = clustercenter
        value = new_value
        mindistance = distance
    dx = least.x - mycenter.x
    dy = least.y - mycenter.y
    destination = Unit(None, dx, dy)
    if aviaspeedfactor != 1:
      s.current_action.appendleft(move(destination,
                                       max_speed = aviaspeedfactor*max_speed))
      s.current_action.appendleft(group(gr, action = ActionType.DISMISS))
      s.current_action.appendleft(select_vehicles(marea, group = gr + 1))
    elif len(myg & aviasupport) == 0:
      aviacenter = get_square(vs.resolve(aviasupport)).get_center()
      ddx = copysign(100*max_speed, dx)
      ddy = copysign(100*max_speed, dy)
      overmain = Unit(None, mycenter.x-aviacenter.x+ddx,
                      mycenter.y-aviacenter.y+ddy)
      s.current_action.appendleft(move(overmain,
                                       max_speed = 2*max_speed))
      s.current_action.appendleft(group(gr, action = ActionType.ASSIGN))
      s.current_action.appendleft(select_vehicles(marea, group = gr + 1))
    s.current_action.appendleft(move(destination, max_speed = max_speed))
  return do_move

def hunt(group: int, game: Game):
  def do_hunt(s: MyStrategy, w: World, m: Move):
    vs = s.worldstate.vehicles
    myv = list(vs.resolve(vs.by_group[group]))
    mya = get_square(myv)
    density = len(myv)/mya.area()
    print("Density is: " + str(density))
    print("Area is: " + str(mya))
    print("Amount is: " + str(len(myv)))
    if density < criticaldensity:
      s.current_action += deque([hurricane(group), hunt(group, game)])
    else:
      huntchain = deque([
        select_vehicles(s.full_area, group = group),
        move_to_enemies(group, game.tank_speed * game.swamp_terrain_speed_factor),
        wait(100),
        hunt(group, game)
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
    self.free_groups = set(range(game.max_unit_group+1))
    self.effectiveness = dict()
    def construct(t, ending = "durability", vt = None):
      if ending == "durability" or vt is None:
        name = typebyname[a] + "_durability"
      else:
        clas = None
        if vt in types[FLYERS]:
          clas = "_aerial_"
        else:
          clas =  "_ground_"
        name = typebyname[t] + clas + ending
      if hasattr(game, name):
        return getattr(game, name)
      return 0
    def positive(a):
      if a < 0:
        return 0
      return a
    for a in typebyname.keys():
      self.effectiveness[a] = dict()
      for d in typebyname.keys():
        self.effectiveness[a][d] = (
          positive(construct(a, "damage", d)-construct(d, "defence", a))
          /construct(d))
    #print(self.effectiveness)
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
        select_vehicles(self.full_area, vtype = VehicleType.HELICOPTER),
        select_vehicles(self.full_area, vtype = VehicleType.FIGHTER,
                        action = ActionType.ADD_TO_SELECTION),
        group(2),
        select_vehicles(self.full_area),
        group(1),
        at_flag("formation_done", 1, deque([
            hunt(1, game)
          ]))
        ])
      self.current_action += shuffle(self)
    self.analyze(me, world, game)
    if len(self.current_action) > 0 and self.actionsRemaining > 0 and self.waiter < world.tick_index:
      while len(self.current_action) > 0:
        act = self.current_action.popleft()
        act(self, world, move)
        if move.action != ActionType.NONE:
          self.actionsRemaining -= 1
          break
    elif self.actionsRemaining > 0:
      to_remove = list()
      for i in reversed(self.events):
        if i(self, world):
          to_remove.append(i)
      for i in to_remove:
        self.events.remove(i)

