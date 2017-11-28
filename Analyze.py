from model.World import World
from model.FacilityType import FacilityType
from model.Game import Game
from collections import defaultdict
from Utils import Area,  FLYERS, types, typebyname


class TaggedDict(dict):
  def __init__(self, data):
    dict.__init__(self)
    for i in data:
      self[i.id] = i

  def resolve(self, data: set):
    return map(lambda i: self[i], data)

class clusterdict(defaultdict):
  def __init__(self, clusterizer: callable):
    defaultdict.__init__(self, clusterizer)
    self.on_miss = clusterizer
  def __missing__(self, v):
    return self.on_miss(v)

class Vehicles(TaggedDict):
  def __init__(self, world: World):
    self.me = world.get_my_player().id
    self.opponent = world.get_opponent_player().id
    self.selected = set()
    self.by_player = defaultdict(set)
    self.by_type = defaultdict(set)
    self.by_group = defaultdict(set)
    self.by_cluster_dict = dict()
    self.updated = set()
    self.damaged = set()
    TaggedDict.__init__(self, world.new_vehicles)
    for i in world.new_vehicles:
      self.by_player[i.player_id].add(i.id)
      self.by_type[i.type].add(i.id)
      self.updated.add(i.id)

  def by_cluster(self, pid: int):
    if not (pid in self.by_cluster_dict):
      self.by_cluster_dict[pid] = self.clusterize(self.by_player[pid])
    return self.by_cluster_dict[pid]

  def clusterize(self, units: set, thresh = 10, griddensity = 12):
    ## returns set of clusters
    ## every cluster is a frozen set of vehicle ids
    clusters = set()
    allclusters = set()
    threshhood = thresh*thresh
    grid = defaultdict(lambda: defaultdict(set))
    # sort units by grid cells
    for id in units:
      unit = self[id]
      gridx = int(unit.x // griddensity)
      gridy = int(unit.y // griddensity)
      grid[gridx][gridy].add(id)
    for id in units:
      #assigned = False
      # check if unit already in one of the clusters
      if id in allclusters:
        continue
#      for c in clusters:
#        if id in c:
#          assigned = True
#          break
 #     if not assigned:
      # if it is a standalone unit lets make new cluster for it
      unit = self[id]
      newcluster = set()
      newcluster.add(id)
      # now lets check all units in neighbour grid cells if
      # they are may be attached to our cluster
      gridx = int(unit.x // griddensity)
      gridy = int(unit.y // griddensity)
      for gx in range(gridx-1, gridx+2):
        for gy in range(gridy-1, gridy+2): # 9 iterations
          for nid in grid[gx][gy]:
            # triple for loop eeew!
            # now lets check distance to neighbour point
            unid = self[nid]
            distance = unit.get_squared_distance_to(unid.x, unid.y)
            if distance < threshhood:
              newcluster.add(nid)
      # our new cluster contains both of new points and probably points
      # from other clusters. lets merge those clusters with new and remove them
      # after the fact
      #print("New cluster contains: ",  len(newcluster))
      to_remove = set()
      for c in clusters:
        if c & newcluster:
          #print("Detected intersection with ",  c,  ", merging")
          newcluster |= c
          to_remove.add(c)
      #print("Will be removed:", to_remove)
      clusters -= to_remove
      # after all lets add our new clusters to others
      clusters.add(frozenset(newcluster))
      allclusters |= newcluster
    #print("Final clusters:",  clusters)
    return clusters

  def in_area(self, a: Area):
    result = set()
    for k, v in self.items():
      if a.is_inside(v):
        result.add(k)
    return result

  def update(self, world: World):
    self.by_cluster_dict = dict()
    for i in world.new_vehicles:
      if not (i.id in self):
        self[i.id] = i
        self.by_player[i.player_id].add(i.id)
        self.by_type[i.type].add(i.id)
    self.updated = set()
    mine = self.by_player[self.me]
    for i in world.vehicle_updates:
      if i.durability == 0:
        self.pop(i.id, None) # remove dead vehicle
        for s in self.by_player.values():
          s.discard(i.id)
        for s in self.by_type.values():
          s.discard(i.id)
        for s in self.by_group.values():
          s.discard(i.id)
        self.selected.discard(i.id)
      else:
        unit = self[i.id]
        if unit.x != i.x or unit.y != i.y:
          self.updated.add(i.id)
          unit.x = i.x
          unit.y = i.y
        if i.id in mine:
          if i.selected:
            self.selected.add(i.id)
          else:
            self.selected.discard(i.id)
          if len(i.groups) != len(unit.groups):
            newgroups = frozenset(i.groups)
            oldgroups = frozenset(unit.groups)
            for g in newgroups - oldgroups:
              self.by_group[g].add(i.id)
            for g in oldgroups - newgroups:
              self.by_group[g].discard(i.id)
            unit.groups = i.groups
        if i.durability != unit.durability:
          durpercent = i.durability / unit.max_durability
          if durpercent < 0.7:
            self.damaged.add(i.id)
          elif durpercent > 0.8:
            self.damaged.discard(i.id)
          unit.durability = i.durability
        #unit.update(i)

class Facilities(TaggedDict):
  def __init__(self, world: World):
    self.by_type = dict()
    self.by_player = defaultdict(set)
    self.by_type[FacilityType.CONTROL_CENTER] = set()
    self.by_type[FacilityType.VEHICLE_FACTORY] = set()
    TaggedDict.__init__(self, world.facilities)
    self.me = world.get_my_player().id
    self.neutral = -1
    self.opponent = world.get_opponent_player().id
    self.update(world)
    for i in world.facilities:
      self.by_type[i.type].add(i.id)

  def update(self, world: World):
    for i in [self.neutral, self.me, self.opponent]:
      self.by_player[i].clear()
    for i in world.facilities:
      self[i.id].vehicle_type = i.vehicle_type
      self[i.id].production_progress = i.production_progress
      self.by_player[i.owner_player_id].add(i.id)


class WorldState:
  def __init__(self, world: World, game: Game):
    self.vehicles = Vehicles(world)
    self.facilities = Facilities(world)
    self.get_opponent_and_me(world)
    self.calculate_effectiveness(game)

  def calculate_effectiveness(self, game: Game):
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

  def get_opponent_and_me(self, w: World):
    if w.players[0].me:
      self.me = w.players[0]
      self.opponent = w.players[1]
    else:
      self.me = w.players[1]
      self.opponent = w.players[0]

  def update(self, world: World):
    self.vehicles.update(world)
    self.facilities.update(world)
    self.get_opponent_and_me(world)

