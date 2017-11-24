from model.ActionType import ActionType
from model.Game import Game
from model.Move import Move
from model.Player import Player
from model.World import World
from model.FacilityType import FacilityType
from model.VehicleType import VehicleType
from model.Unit import Unit
from Analyze import WorldState
from collections import deque
from Utils import Area
from Formation import GroundFormation, AerialFormation
from deadcode import shuffle, at_flag,  wait, group, select_vehicles, devide, move as moveto

def make_formation(i):
  def do_make(s, w: World, g: Game, m: Move):
    #print("Formation was made!")
    newaerial = AerialFormation(2*i+1)
    new_formation = GroundFormation(2*i+2)
    s.formations.append(newaerial)
    s.formations.append(new_formation)
  return do_make

class MyStrategy:
  action_queue = deque()
  events = list()
  flags = dict()
  waiter = -1
  nomoveturns = 0
  def init(self, me: Player, world: World, game: Game):
    self.priority = False
    self.no_priority_change = 0
    self.full_area = Area(0.0,world.width,0.0,world.height)
    self.formations = list()
    self.free_groups = set(range(1,game.max_unit_group+1))
    self.worldstate = WorldState(world,  game)

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
      self.action_queue += shuffle(self)
      def each(i, pa, fa):
        return deque([
          select_vehicles(pa, vtype=VehicleType.FIGHTER),
          select_vehicles(pa, vtype=VehicleType.HELICOPTER, action=ActionType.ADD_TO_SELECTION),
          moveto(Unit(None, (1-i)*100, (i-1)*10)),
          group(2*i+1),
          wait(30*(1-i)),
          select_vehicles(pa),
          select_vehicles(pa, group=2*i+1, action=ActionType.DESELECT),
          moveto(Unit(None, (1-i)*100, (i-1)*10)),
          group(2*i+2),
          wait(30*(1-i)),
          make_formation(i)
        ])
      self.action_queue.append(at_flag("formation_done",  1, deque([
#        devide(self.worldstate.vehicles.by_player[self.worldstate.vehicles.me], each, 2,  "done")
        select_vehicles(self.full_area, vtype=VehicleType.FIGHTER),
        select_vehicles(self.full_area, vtype=VehicleType.HELICOPTER, action=ActionType.ADD_TO_SELECTION),
        group(1),
        wait(1),
        select_vehicles(self.full_area),
        select_vehicles(self.full_area, group=1, action=ActionType.DESELECT),
        group(2),
        wait(1),
        make_formation(0)
      ])))
    self.analyze(me, world, game)
    # Doing actions and triggering events
    if len(self.action_queue) > 0 and self.actionsRemaining > 0 and self.waiter < world.tick_index:
      while len(self.action_queue) > 0:
        act = self.action_queue.popleft()
        act(self, world, game, move)
        if move.action != ActionType.NONE:
          self.actionsRemaining -= 1
          break
    elif self.actionsRemaining > 0:
      to_remove = set()
      if type(self.priority) is int and self.no_priority_change < 10 and self.priority < len(self.formations):
        #print("Selecting again by priority:",  self.priority)
        f = self.formations[self.priority]
        if len(f.units(self.worldstate.vehicles)) == 0:
          to_remove.add(self.priority)
          self.priority = None
        else:
          f.tick(self.worldstate, world, me, game, move)
      if move.action and move.action != ActionType.NONE:
        self.actionsRemaining -= 1
        self.no_priority_change += 1
      else:
        for i,  f in enumerate(self.formations):
          if i == self.priority:
            continue
          if len(f.units(self.worldstate.vehicles)) == 0:
            to_remove.add(i)
            continue
          f.tick(self.worldstate, world, me, game, move)
          if move.action and move.action != ActionType.NONE:
            self.priority = i
            self.no_priority_change = 0
            #print("Setting priority to:",  i)
            self.actionsRemaining -= 1
            break
      if len(to_remove) > 0:
        for i in to_remove:
          if self.priority == i:
            self.priority = None
          self.formations.pop(i)
      # events no longer needed after the end of formation
      to_remove = list()
      for i in reversed(self.events):
        if i(self, world):
          to_remove.append(i)
      for i in to_remove:
        self.events.remove(i)

