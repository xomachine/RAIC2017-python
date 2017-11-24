from math import pi,  atan2
from model.Unit import Unit
from model.VehicleType import VehicleType
from model.Game import Game
from model.Vehicle import Vehicle
from model.World import World

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
  def from_units(units: list):
    result = Area(1000, 0, 1000, 0)
    for v in units:
      if v.x < result.left:
        result.left = v.x
      if v.x > result.right:
        result.right = v.x
      if v.y < result.top:
        result.top = v.y
      if v.y > result.bottom:
        result.bottom = v.y
    return result
  def get_center(self):
    return Unit(None, (self.left + self.right)/2, (self.top + self.bottom)/2)
  def mirror(self):
    return Area(self.top, self.bottom, self.left, self.right)
  def copy(self):
    return Area(self.left, self.right, self.top, self.bottom)
  def is_inside(self, point):
    return (point.x <= self.right and point.x >= self.left and
            point.y >= self.top and point.y <= self.bottom)
  def area(self):
    width = (self.right - self.left)
    height = (self.bottom - self.top)
    return  width * height + abs(width - height)**2
  def __str__(self):
    return str(self.left) + " <> " + str(self.right) + ":" + str(self.top) + "^V" + str(self.bottom)

def normalize_angle(angle):
  while angle > pi:
    angle -= 2*pi
  while angle < -pi:
    angle += 2*pi
  return angle

def get_angle_between(a: Unit, b: Unit):
  return atan2((a.y - b.y), (a.x - b.x))

def get_vision_range(w: World, vehicle: Vehicle,  game: Game):
  grid = 32
  vehicle_col = int(vehicle.x // grid)
  vehicle_row = int(vehicle.y // grid)
  if vehicle.type in types[GROUNDERS]:
    dct = ["plain",  "swamp", "forest"]
    terrain = w.terrain_by_cell_x_y[vehicle_col][vehicle_row]
    attrname = dct[terrain] + "_terrain_vision_factor"
  else:
    dct = ["clear",  "cloud", "rain"]
    weather = w.weather_by_cell_x_y[vehicle_col][vehicle_row]
    attrname = dct[weather] + "_weather_vision_factor"
  return vehicle.vision_range * getattr(game, attrname)

def get_center(v: list):
  vehicles = list(v)
  length = len(vehicles)
  assert(length > 0)
  center = length//2
  xsort = sorted(vehicles, key=lambda x: x.x)
  ysort = sorted(vehicles, key=lambda x: x.y)
  return Unit(None, xsort[center].x, ysort[center].y)

def get_min_speed(game: Game, vehicles, units: set):
  slowname = get_slowest(vehicles, units)
  slowspeed = getattr(game, slowname + "_speed")
  if slowname in ["tank",  "ifv"]:
    return slowspeed * game.swamp_terrain_speed_factor
  else:
    return slowspeed * game.rain_weather_speed_factor

def get_slowest(vehicles, units: set):
  if vehicles.by_type[VehicleType.TANK] & units:
    return "tank"
  elif (vehicles.by_type[VehicleType.IFV] | vehicles.by_type[VehicleType.ARRV]) & units:
    return "ifv"
  elif vehicles.by_type[VehicleType.HELICOPTER] & units:
    return "helicopter"
  else:
    return "fighter"
