from model.ActionType import ActionType
from model.Game import Game
from model.Move import Move
from model.Player import Player
from model.World import World
from model.FacilityType import FacilityType
from Analyze import WorldState
from collections import deque
from Utils import Area
from Formation import GroundFormation
from deadcode import shuffle, at_flag,  wait, group, select_vehicles

def make_formation(s, w: World, g: Game, m: Move):
  print("Formation was made!")
  new_formation = GroundFormation(1)
  s.formations.append(new_formation)

class MyStrategy:
  action_queue = deque()
  events = list()
  flags = dict()
  waiter = -1
  nomoveturns = 0
  def init(self, me: Player, world: World, game: Game):
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
      self.action_queue.append(at_flag("formation_done",  1, deque([
        select_vehicles(self.full_area),
        group(1),
        wait(1),
        make_formation
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
      for f in self.formations:
        f.tick(self.worldstate, world, me, game, move)
        if move.action != ActionType.NONE:
          self.actionsRemaining -= 1
          break
      to_remove = list()
      for i in reversed(self.events):
        if i(self, world):
          to_remove.append(i)
      for i in to_remove:
        self.events.remove(i)

