from model.World import World
from model.FacilityType import FacilityType
from collections import defaultdict
from Utils import Area
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
    self.by_cluster = clusterdict(lambda x: self.clusterize(self.by_player[x]))
    self.updated = set()
    self.damaged = set()
    TaggedDict.__init__(self, world.new_vehicles)
    for i in world.new_vehicles:
      self.by_player[i.player_id].add(i.id)
      self.by_type[i.type].add(i.id)
      self.updated.add(i.id)

  def clasterize(self, units: set, thresh = 10, griddensity = 10):
    ## returns set of clusters
    ## every cluster is a frozen set of vehicle ids
    clusters = list()
    grid = defaultdict(lambda: defaultdict(lambda:set()))
    # sort units by grid cells
    for id in units:
      unit = self[id]
      gridx = unit.x // griddensity
      gridy = unit.y // griddensity
      grid[gridx][gridy].add(id)
    for id in units:
      assigned = False
      # check if unit already in one of the clusters
      for c in clusters:
        if id in c:
          assigned = True
          break
      if not assigned:
        # if it is a standalone unit lets make new cluster for it
        unit = self[id]
        newcluster = set()
        newcluster.add(id)
        # now lets check all units in neighbour grid cells if
        # they are may be attached to our cluster
        gridx = unit.x // griddensity
        gridy = unit.y // griddensity
        for gx in range(gridx-1, gridx+2):
          for gy in range(gridy-1, gridy+2): # 9 iterations
            for nid in grid[gx][gy]:
              # triple for loop eeew!
              # now lets check distance to neighbour point
              distance = unit.get_distance_to_unit(self[nid])
              if distance < thresh:
                newcluster.add(nid)
        # our new cluster contains both of new points and probably points
        # from other clusters. lets merge those clusters with new and remove them
        # after the fact
        to_remove = set()
        for c in clusters:
          if c & newcluster:
            newcluster |= c
            to_remove.add(c)
        clusters -= to_remove
        # after all lets add our new clusters to others
        clusters.add(frozenset(newcluster))
      return clusters

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
        if i.id in mine:
          if i.selected:
            self.selected.add(i.id)
          else:
            self.selected.discard(i.id)
          newgroups = frozenset(i.groups)
          oldgroups = frozenset(unit.groups)
          for g in newgroups - oldgroups:
            self.by_group[g].add(i.id)
          for g in oldgroups - newgroups:
            self.by_group[g].discard(i.id)
        if i.durability / self[i.id].max_durability < 0.55:
          self.damaged.add(i.id)
        else:
          self.damaged.discard(i.id)
        unit.update(i)

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

