from model.ActionType import ActionType
from model.Move import Move
from model.World import World
from model.VehicleType import VehicleType
from Utils import get_center, Area
from Analyze import WorldState, Vehicles
class Action:
  def __init__(self,  action: ActionType = ActionType.NONE):
    self.action = action
  def resolve(self,  move: Move,  ws: WorldState, world: World):
    move.action = self.action

class Event:
  #: Action
  def __init__(self):
   pass
  def at_move_end():
    pass
  def after():
    pass

class MoveAction(Action):
  def __init__(self,  position_obtainer: callable):
    ## position obtainer should return the Unit of target position in absolute coordinates
    Action.__init__(self,  ActionType.MOVE)
    self.position_obtainer = position_obtainer
  def resolve(self,  move: Move,  ws: WorldState,  w: World):
    Action.resolve(move,  ws,  w)
    position = self.position_obtainer(ws,  w)
    current_position = get_center(ws.vehicles.resolve(ws.vehicles.selected))
    move.x = position.x - current_position.x
    move.y = position.y - current_position.y

class RotateAction(Action):
  def __init__(self, epicenter_obtainer: callable):
    ## epicenter_obtainer should return tuple of center Unit and angle
    Action.__init__(self, ActionType.ROTATE)
    self.epicenter_obtainer = epicenter_obtainer
  def resolve(self, move: Move,  ws: WorldState, w: World):
    Action.resolve(self,  move,  ws,  w)
    epicenter = self.epicenter_obtainer(ws,  w)
    move.x = epicenter[0].x
    move.y = epicenter[0].y
    move.angle = epicenter[1]

class Selector(Action):
  def __init__(self,  area: Area,  group: int = -1, vtype: VehicleType = -1,  action = ActionType.CLEAR_AND_SELECT):
    Action.__init__(self, action)
    self.area = area
    self.vehicle_type = vtype
    self.group = group

  def to_set(self,  prev: set,  vehicles: Vehicles):
    if self.group > 0:
      result = vehicles.by_group[self.group]
    else:
      result = vehicles.in_area(self.area) & vehicles.by_player[vehicles.me]
      if self.vehicle_type > 0:
        result &= vehicles.by_type[self.vehicle_type]
    if self.action == ActionType.CLEAR_AND_SELECT:
      return result
    elif self.action == ActionType.ADD_TO_SELECTION:
      return result | prev
    elif self.action == ActionType.DESELECT:
      return prev - result

  def resolve(self,  move: Move,  ws: WorldState, world: World):
    Action.resolve(self,  move,  ws,  world)
    move.left = self.area.left
    move.right = self.area.right
    move.top = self.area.top
    move.bottom = self.area.bottom
    move.group = self.group
    move.vehicle_type = self.vehicle_type

class ActionChain:
  counter = 0
  queue = list() # List of Actions
  last_selection = set()
  def __init__(self):
    pass
  def select(self,  area: Area, group: int = -1, vtype: VehicleType = -1):
    selector = Selector(area,  group,  vtype,  ActionType.CLEAR_AND_SELECT)
    self.queue.append(selector)
    return self
  def add_to_select(self,  area: Area, group: int = -1, vtype: VehicleType = -1):
    selector = Selector(area,  group,  vtype,  ActionType.ADD_TO_SELECTION)
    self.queue.append(selector)
    return self
  def remove_from_select(self,  area: Area, group: int = -1, vtype: VehicleType = -1):
    selector = Selector(area,  group,  vtype,  ActionType.DESELECT)
    self.queue.append(selector)
    return self
  def move(self,  position_obtainer: callable):
    ## returns move_end event
    action = MoveAction(position_obtainer)
    self.queue.append(action)
    return self
  def rotate(self,  epicenter_obtainer: callable):
    self.queue.append(RotateAction(epicenter_obtainer))
    return self
  def nuke(self):
    return self
  def resolve(self, move: Move, ws: WorldState, world: World):
    if len(self.queue) <= self.counter:
      return True
    current_action = self.queue[self.counter]
    self.last_selection = ws.vehicles.selected
    current_action.resolve(move,  ws,  world)
    self.counter += 1
