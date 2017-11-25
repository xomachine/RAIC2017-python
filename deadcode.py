# deadcode
from model.ActionType import ActionType
from model.Game import Game
from model.Move import Move
from model.World import World
from model.Unit import Unit
from model.VehicleType import VehicleType
from Analyze import Vehicles
from Utils import types,  GROUNDERS, FLYERS, movables, typebyname
from collections import deque
from Utils import Area,  get_center
from functools import reduce
from math import pi, sqrt
fuzz = 1

criticaldensity = 1 / 25  # how tight should the vehicles stay

def fill_flag(name: str):
  def do_fill(s, w: World, g: Game, m: Move):
    #print("Filling flag: " + name)
    if name in s.flags:
      s.flags[name] += 1
    else:
      s.flags[name] = 1
  return do_fill

def at_flag(name: str, count: int, actions: deque):
  ## Adds actions to current queue if flag filled
  def event(s, w: World, c: int = count):
    if (not (name in s.flags)) or s.flags[name] >= c:
      #print("Got " + str(c) + " in " + name)
      ## If dict key does not exist, it means that previous handler just
      ## have deleted it and flag had filled before
      s.action_queue = actions + s.action_queue
      if name in s.flags:
        s.flags.pop(name)
      return True
    return False
  def do_add_event(s, w: World, g: Game, m: Move):
    if not (name in s.flags):
      s.flags[name] = 0
    #print("Waiting " + str(count) + " on flag: " + name)
    s.events.append(event)
  return do_add_event

def at_move_end(watchers: set, actions: deque):
  name = "move_end:" + str(hash(frozenset(watchers)))
  def do_eventme(s, w: World):
    intersect = s.worldstate.vehicles.updated & watchers
    if (not (name in s.flags)) or s.flags[name] >= 2:
      #print("Move ended for " + name)
      if name in s.flags:
        s.flags.pop(name)
      s.action_queue = actions + s.action_queue
      return True
    if len(intersect) == 0:
      s.flags[name] += 1
    else:
      s.flags[name] = 0
    return False
  def do_waitme(s, w: World, g: Game, m: Move):
    s.events.append(do_eventme)
    #print("Waiting move end for set:" + name)
    s.flags[name] = 0
  return do_waitme

def wait(ticks: int):
  counter = ticks
  def do_wait(s, w: World, g: Game, m: Move):
    s.waiter = w.tick_index + counter
  return do_wait

def after(ticks: int, actions: list):
  def add_event(s, w: World, g: Game, m: Move):
    target_tick = w.tick_index + ticks
    def event(ss, ww: World, tt = target_tick):
      if ww.tick_index >= tt:
        ss.action_queue = deque(actions) + ss.action_queue
    s.events.append(event)
  return add_event

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
  def do_rotate(s, w: World, g: Game, m: Move):
    m.action = ActionType.ROTATE
    m.angle = angle
    m.max_angular_speed = max_speed
    m.x = center.x
    m.y = center.y
  return do_rotate

def move(destination: Unit, max_speed: float = 0.0):
  def do_move(s, w: World, g: Game, m: Move):
    m.action = ActionType.MOVE
    m.x = destination.x
    m.y = destination.y
    #print("Moving to: " + str(destination.x) + ":" + str(destination.y))
    m.max_speed = max_speed
  return do_move

def group(gnum: int, action: range(4, 7) = ActionType.ASSIGN):
  def do_group(s, w: World, g: Game, m: Move):
    m.action = action
    m.group = gnum
    if action == ActionType.ASSIGN:
      s.free_groups.discard(gnum)
    elif action == ActionType.DISBAND:
      s.free_groups.add(gnum)
  return do_group

def scale(center: Unit, factor: float):
  def do_scale(s, w: World, g: Game, m: Move):
    m.action = ActionType.SCALE
    m.factor = factor
    m.x = center.x
    m.y = center.y
  return do_scale

def select_vehicles(area: Area, vtype: VehicleType = None, group: int = 0,
                    action: range(1, 4) = ActionType.CLEAR_AND_SELECT):
  def do_select(s, w: World, g: Game, m: Move, a = area):
    m.action = action
    #print("Selecting: " + str(a))
    m.left = a.left - fuzz
    m.right = a.right + fuzz
    m.top = a.top
    m.bottom = a.bottom
    m.group = group
    m.vehicle_type = vtype
  return do_select

def hurricane(group: int):
  name = "hurricaned:" + str(group)
  def do_hurricane(s, w:World, g: Game, m: Move):
    vs = s.worldstate.vehicles
    pv = vs.by_group[group]
    myv = list(vs.resolve(pv))
    #print("Hurricane!")
    #print(mya)
    epicenter = get_center(myv)
    def scale_hur():
      return [
        select_vehicles(s.full_area, group = group),
        scale(epicenter, 0.1),
      ]
    def rotate_hur(angle: float):
      return [
        select_vehicles(s.full_area, group = group),
        rotate(angle, epicenter),
      ]
    result = deque(
      scale_hur() +
      [
        after(30, rotate_hur(pi/2)),
        after(60, scale_hur()),
        after(90, rotate_hur(-pi/2)),
        after(120, scale_hur()),
        after(150, [fill_flag(name)]),
      ]
    )
    s.action_queue = result + s.action_queue
  return do_hurricane

def devide(unitset: set, each: callable, parts: int, name: str, horizontal = False):
  ## devide unitset to `parts` parts and do `each` with each part
  ## each must be a callable that returns deque of actual actions and gets
  ## a group number as argument. actions will be applied in order from
  ## central part to edges
  ## the last argument is an event name which will be fired
  ## when devision is done. (at_flag)
  halfparts = parts // 2
  ordered = sorted(range(parts), key = lambda x: abs(x-halfparts))
  tmpname = "devision:" + str(hash(frozenset(unitset)))
  def do_devide(s, w: World, g: Game, m: Move):
    vs = s.worldstate.vehicles
    # to avoid non existing units we using intersection with
    # all players units
    pv = (vs.by_player[vs.me] & unitset)
    units = vs.resolve(pv)
    uarea = Area.from_units(units)
    if horizontal:
      uarea = uarea.mirror()
    step = (uarea.bottom - uarea.top) / parts
    for i in ordered:
      pa = s.full_area.copy()
      pa.top = step * i + uarea.top
      pa.bottom = step * (i+1) + uarea.top
      if horizontal:
        vehicles = vs.in_area(pa.mirror())
        s.action_queue = (do_and_check(each(i, pa.mirror(), uarea.mirror()),
                                         tmpname, vehicles) + s.action_queue)
      else:
        vehicles = vs.in_area(pa)
        s.action_queue = (do_and_check(each(i, pa, uarea), tmpname, vehicles)
                            + s.action_queue)
    s.action_queue.appendleft(at_flag(tmpname, parts,
                                         deque([fill_flag(name)])))
  return do_devide

def nuke_it(target: Unit, navigator: int):
  def do_nuke(s, w: World, g: Game, m: Move):
    m.action = ActionType.TACTICAL_NUCLEAR_STRIKE
    m.x = target.x
    m.y = target.y
    m.vehicle_id = navigator
  return do_nuke

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
  def do_tight(s, w: World, g: Game, m: Move):
    vs = s.worldstate.vehicles
    pv = vs.by_player[vs.me]
    actualgroup = group & pv
    def each(i, partarea, fullarea):
      #target = Unit(None, 0, (1 - 2 * i) * 1000)
      center = fullarea.get_center()
      return deque([
        #select_vehicles(partarea),
        #move(target),
        #wait(50),
        select_vehicles(partarea),
        scale(center, 0.1),
      ])
    s.action_queue.appendleft(devide(actualgroup, each, 2, name))
  return do_tight

def initial_shuffle():
  ## Shuffles initially spawned groups of units into one
  ## Units should be initially set in one line
  ## Returns a closure to place into MyStrategy.action_queue
  def do_shuffle(s, w: World, g: Game, m: Move):
    pass
  return do_shuffle

def do_shuffle(ss, w: World, g: Game, m: Move):
  vss = ss.worldstate.vehicles
  pv = vss.by_player[vss.me]
  myv = vss.resolve(pv)
  mya = Area.from_units(myv)
  #print("Area after alighment")
  #print(mya)
  parts = 10
  step = (mya.bottom - mya.top) / parts
  central = ss.full_area.copy()
  fragment_area = Area.from_units(vss.resolve(pv & vss.by_type[VehicleType.IFV]))
  fragment = fragment_area.right - fragment_area.left
  central.left = (mya.left + mya.right - fragment)/2
  central.right = central.left + fragment
  righter = ss.full_area.copy()
  righter.right = mya.right
  righter.left = mya.right - fragment
  lefter = ss.full_area.copy()
  lefter.left = mya.left
  lefter.right = mya.left + fragment
  #fourth_turn = deque([
    #select_vehicles(ss.full_area),
    #rotate(-pi/2, Unit(None, central.right + fragment/2, mya.top + fragment*2))
  def halfrotate(i, a, f):
    pass
    #if i == 0:
    #  return deque()
    #else:
    #  rcenter = f.get_center()
    #  rcenter.x = f.left - 1 # minus unit radius
    #  return deque([select_vehicles(a), rotate(pi, rcenter)])
#  def when_done(s: MyStrategy, w: World, g: Game, m: Move):
#    vs = s.worldstate.vehicles
#    theformation = Formation(s, vs.by_player[vs.me], "formation_done")
#    s.formations.append(theformation)
#    s.action_queue.appendleft(at_flag("grouped:formation_done", 1, deque([theformation.setdistance(200)])))
  fifth_turn = deque([
    #when_done,
    select_vehicles(ss.full_area),
    rotate(pi/4, Unit(None, central.left, mya.bottom)),
    at_move_end(pv, deque([fill_flag("formation_done")]))
#    fill_flag("formation_done")
    #at_flag("grouped", 1, deque([fill_flag("formation_done")])),
    #devide(vss.by_group[1], halfrotate, 2, "grouped")
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
  ss.action_queue.appendleft(devide(pv, each, parts, "loosed"))
  ss.action_queue.appendleft(at_flag("loosed", 1, second_turn))

def initial_compact(s):
  ## Compactifies the initial spawn into one line
  ## At the end of process will set the "compacted" flag
  ## Returns deque with actions. s - MyStrategy
  result = deque()
  vs = s.worldstate.vehicles
  pv = vs.by_player[vs.me]
  # hardcoded, no way to obtain dynamicaly
  spawnarea = Area(18, 220, 18, 220)
  squadarea = Area.from_units(vs.resolve(vs.by_type[VehicleType.IFV] & pv))
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
  for t in [GROUNDERS, FLYERS]:
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
    #print("Type " + str(t) + " has " + str(squadsfromset) + " squads by columns")
    #print(empties)
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
            #print("Checking for obstacles...")
            for lno, line in enumerate(lines):
              if line.is_inside(sample):
                #print("... at line " + str(lno))
                obstacle = (vs.in_area(line) & vs.in_area(columns[1]) &
                            sets[t])
                break
            if len(obstacle) > 0:
              #print("Obstacle detected")
              obstacletype = vs[obstacle.pop()].type
              if obstacletype == VehicleType.TANK:
                #print("It is tank, lets find something else to move")
                continue
              else:
                tcol = empties.pop()
                empties.add(1)
                target = Unit(None, columns[tcol].left - columns[1].left, 0)
                #print("Move obstacle from 1 to " + str(tcol))
                result += do_and_check([
                  select_vehicles(s.full_area, vtype = obstacletype),
                  move(target)], name, unitsfromset[i])
                registredflags += 1
          tcol = empties.pop()
          target = Unit(None, columns[tcol].left - columns[i].left, 0)
          #print("Move from " + str(i) + " to " + str(tcol))
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

valcache = dict()
accesses = 0
def calculate(eff: dict, v: Vehicles, game: Game, my: set, enemies: set):
  result = 0.0
  global valcache
  global accesses
  if not enemies  or not my:
    return len(my) - len(enemies)
  mylens = [0] * 5
  enlens = [0] * 5
  for t in typebyname.keys():
    maxdur = getattr(game, typebyname[t] + "_durability")
    mot = my & v.by_type[t]
    if mot:
      #mysumdur = len(mot) * maxdur
      for vh in v.resolve(mot):
        mylens[t] += vh.durability
      mylens[t] /= maxdur
    eot = enemies & v.by_type[t]
    if eot:
      #ensumdur = maxdur * len(enemies)
      for vh in v.resolve(eot):
        enlens[t] += vh.durability
      enlens[t] /= maxdur
  the_signature = hash((tuple(mylens), tuple(enlens)))
  if the_signature in valcache:
    return valcache[the_signature]
  #print("My lengths:",  mylens)
  #print("Enemy lengths:",  enlens)
  for mt in typebyname.keys():
    mylen = mylens[mt]
    if mylen > 0:
      #print("Calculation for " + typebyname[mt])
      for et in typebyname.keys():
        enlen = enlens[et]
        if enlen > 0:
          corr = (mylen * eff[mt][et] - enlen * eff[et][mt])
          #print("...and " + typebyname[et] + " = " + str(corr))
          result += corr
  accesses += 1
  if accesses > 1000:
    valcache = dict()
  valcache[the_signature] = result
  return result

def by_xy(distance: float, deltas: Unit):
  ## Splits distance to x and y components in relation set via deltas
  if deltas.x == 0:
    newdx = 0
    newdy = distance
  elif deltas.y == 0:
    newdy = 0
    newdx = distance
  else:
    slope = deltas.y/deltas.x
    newdx = sqrt((distance**2)/((slope**2)+1))
    newdy = newdx * slope
  return Unit(None, newdx, newdy)
