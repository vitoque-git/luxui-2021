import math
import sys
import collections
import random

random.seed(50)

from game_state_info.game_state_info import GameStateInfo

from typing import Optional, List, Dict, Tuple, DefaultDict, OrderedDict
from collections import defaultdict

from lux.game import Game, Missions
from lux.game_map import Cell, Position, RESOURCE_TYPES
from lux.constants import Constants
from lux import annotate

from UnitInfo import UnitInfo
from GameInfo import GameInfo
from MoveHelper import MoveHelper
from lux.game_objects import CityTile, Unit, City, DIRECTIONS

import clusters.cluster_controller as ClusterController
from clusters.cluster import Cluster
import resources.resource_helper as ResourceService
from clusters.cluster_controller import ClusterControl
import maps.map_analysis as MapAnalysis


# todo
# optimise more first move in case enemy is just adjacent (586755628)
# - optimise where create worker
# do not build small city with coal and uranium when close city needs fuel (882001378)
# extend first move to any movement from city to resource
# if moving to a city, remove move that move via another city, we can use a similar approach to cluster and have returner pointing to a city in role, and avoid others
# turn 200 seems to be a good turn to go and conquer wood unexplored wood clusters as it seems to make till 360
# remove from resources guarded clusters
# for path as a traveller  favour tiles with resources
# for path as a resource seek favour tiles with cities

### Define helper functions

# this snippet finds all resources stored on the map and puts them into a list so we can search over them


def get_4_directions() -> [DIRECTIONS]:
    return [DIRECTIONS.SOUTH, DIRECTIONS.NORTH, DIRECTIONS.WEST, DIRECTIONS.EAST]


def directions_to(start_pos: 'Position', target_pos: 'Position') -> [DIRECTIONS]:
    """
    Return closest position to target_pos from this position
    """
    check_dirs = [
        DIRECTIONS.NORTH,
        DIRECTIONS.EAST,
        DIRECTIONS.SOUTH,
        DIRECTIONS.WEST,
    ]
    closest_dist = start_pos.distance_to(target_pos)
    closest_dirs = [DIRECTIONS.CENTER]
    for direction in check_dirs:
        newpos = start_pos.translate(direction, 1)
        dist = target_pos.distance_to(newpos)
        if dist < closest_dist:
            closest_dirs = [direction]
            closest_dist = dist
        elif dist == closest_dist:
            closest_dirs.append(direction)
            closest_dist = dist
    return closest_dirs


def find_closest_city_tile(pos, player) -> CityTile:
    closest_city_tile = None
    if len(player.cities) > 0:
        closest_dist = math.inf
        # the cities are stored as a dictionary mapping city id to the city object, which has a citytiles field that
        # contains the information of all citytiles in that city
        for k, city in player.cities.items():
            for city_tile in city.citytiles:
                dist = city_tile.pos.distance_to(pos)
                if dist < closest_dist:
                    closest_dist = dist
                    closest_city_tile = city_tile
    return closest_city_tile


def find_closest_adjacent_enemy_city_tile(pos, opponent) -> CityTile:
    closest_city_tile = None
    if len(opponent.cities) > 0:
        closest_dist = math.inf
        # the cities are stored as a dictionary mapping city id to the city object, which has a citytiles field that
        # contains the information of all citytiles in that city
        for k, city in opponent.cities.items():
            for city_tile in city.citytiles:
                dist = city_tile.pos.distance_to(pos)
                if dist < closest_dist:
                    closest_dist = dist
                    closest_city_tile = city_tile

    # and now one step back
    return closest_city_tile


def is_cell_empty(pos, game_state) -> bool:
    cell = game_state.map.get_cell(pos.x, pos.y)
    result = (not cell.has_resource()) and cell.citytile is None;
    # print("- ", pos, 'empty',result, file=sys.stderr)
    return result


# snippet to find the all city tiles distance and sort them.
def find_number_of_adjacent_city_tile(pos, player) -> int:
    number = 0
    for city in player.cities.values():
        for citytiles in city.citytiles:
            if citytiles.pos.is_adjacent(pos):
                number = number + 1

    return number


def find_all_adjacent_empty_tiles(game_state, pos) -> List[Position]:
    adjacent_positions = [Position(pos.x, pos.y + 1), Position(pos.x - 1, pos.y), Position(pos.x, pos.y - 1),
                          Position(pos.x + 1, pos.y)];
    empty_tiles = []
    for adjacent_position in adjacent_positions:
        if not is_position_valid(adjacent_position, game_state):
            continue
        try:
            if game_state.map.get_cell_by_pos(adjacent_position) is None:
                continue
            if not adjacent_position.is_adjacent(pos):
                # strangely the above return cell on the other side of the map
                continue
            if is_cell_empty(adjacent_position, game_state):
                empty_tiles.append(adjacent_position)
        except Exception:
            continue
    return empty_tiles


def is_position_valid(position, game_state) -> bool:
    return not (position.x < 0 or position.y < 0 \
                or position.x >= game_state.map_width or position.y >= game_state.map_height)


def adjacent_empty_tile_favor_close_to_city(empty_tyles, game_state, player) -> Optional[Cell]:
    if len(empty_tyles) == 0:
        return None
    elif len(empty_tyles) == 1:
        return game_state.map.get_cell_by_pos(empty_tyles[0])
    else:
        # print("Trying to solve which empty one is close to most cities tiles", file=sys.stderr)
        results = {}
        for adjacent_position in empty_tyles:
            number_of_adjacent = find_number_of_adjacent_city_tile(adjacent_position, player)
            results[number_of_adjacent] = adjacent_position
            # print("- ",adjacent_position,number_of_adjacent, file=sys.stderr)
        results = dict(sorted(results.items()))
        # ordered by number of tiles, so we take last element
        # print("results", results, file=sys.stderr)
        result = list(results.values())[-1]
        # print("Return", result, file=sys.stderr)
        return game_state.map.get_cell_by_pos(result)


def empty_tile_near_wood_and_city(empty_tiles, wood_tiles, game_state, player) -> Optional[Cell]:
    results = {}
    for adjacent_position in empty_tiles:
        number_of_adjacent = find_number_of_adjacent_city_tile(adjacent_position, player)
        if number_of_adjacent > 0 and ResourceService.is_position_adjacent_to_resource(wood_tiles, adjacent_position):
            results[number_of_adjacent] = adjacent_position
            # print("- ",adjacent_position,number_of_adjacent, file=sys.stderr)

    results = dict(sorted(results.items()))
    # ordered by number of tiles, so we take last element
    # print("results", results, file=sys.stderr)
    if len(results) == 0:
        # print("Return None", file=sys.stderr)
        return None
    else:
        result = list(results.values())[-1]

    # print("Return", result, file=sys.stderr)
    return game_state.map.get_cell_by_pos(result)


# snippet to find the all city tiles distance and sort them.
def find_city_tile_distance(pos: Position, player, unsafe_cities) -> Dict[CityTile, Tuple[int, int,int,str]]:
    city_tiles_distance: Dict[CityTile, Tuple[int, int, int,str]] = {}
    if len(player.cities) > 0:
        closest_dist = math.inf
        # the cities are stored as a dictionary mapping city id to the city object, which has a citytiles field that
        # contains the information of all citytiles in that city
        for k, city in player.cities.items():
            if city.cityid in unsafe_cities:
                for city_tile in city.citytiles:
                    dist = city_tile.pos.distance_to(pos)
                    # order by distance asc, autonomy desc
                    city_tiles_distance[city_tile] = (dist, get_autonomy_turns(city),-len(city.citytiles),city.cityid)
    # order by
    # - increasing distance (closest city first),
    # - increasing autonomy (smallest autonomy first)
    # - decreasing size (biggest cities first)

    city_tiles_distance = collections.OrderedDict(sorted(city_tiles_distance.items(), key=lambda x: x[1]))
    #     print(len(city_tiles_distance))
    return city_tiles_distance


def get_random_step(from_pos: Position, move_mapper: MoveHelper) -> DIRECTIONS:
    random_sequence = random.choice([0, 1, 2, 3])
    # randomly choose which sequence to start with, so not to have a rotational probailistic skew
    if random_sequence == 0:
        directions = [DIRECTIONS.SOUTH, DIRECTIONS.NORTH, DIRECTIONS.WEST, DIRECTIONS.EAST]
    elif random_sequence == 1:
        directions = [DIRECTIONS.EAST, DIRECTIONS.SOUTH, DIRECTIONS.NORTH, DIRECTIONS.WEST]
    elif random_sequence == 2:
        directions = [DIRECTIONS.WEST, DIRECTIONS.EAST, DIRECTIONS.SOUTH, DIRECTIONS.NORTH]
    else:
        directions = [DIRECTIONS.NORTH, DIRECTIONS.WEST, DIRECTIONS.EAST, DIRECTIONS.SOUTH]

    for direction in directions:
        if move_mapper.can_move_to_direction(from_pos, direction):
            return direction
    # otherwise
    return DIRECTIONS.CENTER


def cargo_to_string(cargo) -> str:
    return_value = ''
    if cargo.wood > 0:
        return_value = return_value + f"Wood:{cargo.wood}"
    if cargo.coal > 0:
        return_value = return_value + f" Coal:{cargo.coal}"
    if cargo.uranium > 0:
        return_value = return_value + f" Uran:{cargo.uranium}"

    return return_value


def cargo_to_fuel(cargo) -> int:
    return cargo.wood + cargo.coal * 10 + cargo.uranium * 40


game_state = None
unit_info = {}
game_info = GameInfo()
clusters: ClusterControl


def agent(observation, configuration):
    global game_state
    global clusters

    ### Do not edit ###
    if observation["step"] == 0:
        game_state = Game()
        game_state._initialize(observation["updates"])
        game_state._update(observation["updates"][2:])
        game_state.id = observation.player

        # This is the start of the game
        clusters = ClusterControl(game_state)
    else:
        game_state._update(observation["updates"])

    actions = []

    ### AI Code goes down here! ###
    game_state_info: GameStateInfo = GameStateInfo(game_state.turn)

    # the below is very expensive and at the moment is only used to get_direction_to_smart
    # game_state.calculate_features(Missions())
    player = game_state.players[observation.player]
    opponent = game_state.players[(observation.player + 1) % 2]
    move_mapper = MoveHelper(player, opponent, game_state.turn)

    # add debug statements like so!
    if game_state.turn == 0:
        print("Agent is running!", file=sys.stderr)
    print("---------Turn number ", game_state.turn, file=sys.stderr)
    t_prefix = "T_" + str(game_state.turn)
    game_info.update(player, game_state)

    # The first thing we do is updating the cluster.
    # Refer to the cluster class for its attributes.
    clusters.update(game_state, player, opponent)

    # current number of units
    units = len(player.units)
    unit_number = 0

    all_resources_tiles, available_resources_tiles, wood_tiles = ResourceService.find_all_resources(game_state, player)
    if game_state.turn == 0:
        # initial calculations
        initial_city_pos = list(player.cities.values())[0].citytiles[0].pos
        x3: list = get_resources_around(available_resources_tiles, initial_city_pos, 3)
        game_info.at_start_resources_within3 = len(x3)
        print("Resources within distance 3 of", initial_city_pos, "initial pos", len(x3), file=sys.stderr)

        first_best_position = None
        first_move = {}
        for direction in get_4_directions():
            next_pos = initial_city_pos.translate(direction, 1)
            if is_position_valid(next_pos, game_state) and not move_mapper.is_position_enemy_city(next_pos):
                res_2 = len(get_resources_around(wood_tiles, next_pos, 1))
                is_empty = is_cell_empty(next_pos, game_state)
                has_empty_next = len(find_all_adjacent_empty_tiles(game_state, next_pos)) > 0
                print('Resources within 2 of', direction, '=', res_2, ';empty', is_empty,
                      ';emptyNext', has_empty_next, file=sys.stderr)
                first_move[(int(not (is_empty or has_empty_next)),-res_2)] = next_pos

        print('Not Ordered Resources within 2', first_move, file=sys.stderr)
        if len(first_move.keys())>0:
            result = collections.OrderedDict(sorted(first_move.items(), key=lambda x: x[0]))
            print('Ordered Resources within 2',result, file=sys.stderr)
            first_best_position=next(iter(result.values()))
            print('first_best_position', first_best_position, file=sys.stderr)
        # END initial calculations

    # Spawn of new troops and assigment of roles below
    for unit in player.units:
        unit_number = unit_number + 1
        if not unit.id in unit_info:
            # new unit
            unit_info[unit.id] = UnitInfo(unit)
            if game_state.turn == 0 and first_best_position is not None:
                unit_info[unit.id].set_unit_role_traveler(first_best_position, 1)
            elif unit_number == 2 and units == 2:
                unit_info[unit.id].set_unit_role('expander')
            # elif unit_number == 5 and units == 5:
            #    unit_info[unit.id].set_unit_role('hassler')
        else:
            unit_info[unit.id].update(unit, game_state.turn)

    for cluster in clusters.get_clusters():
        print(t_prefix, 'cluster', cluster.to_string_light(), file=sys.stderr)
        if cluster.res_type == RESOURCE_TYPES.WOOD and cluster.has_eq_gr_units_than_res() and cluster.num_units() > 1:
            print(t_prefix, 'cluster', cluster.id, ' is overcrowded, units', cluster.units, file=sys.stderr)

            # find closest cluster (uncontended?)
            next_cluster_dist = math.inf
            next_cluster: Cluster = None
            for next_clust in clusters.get_clusters():
                if next_clust.id != cluster.id and next_clust.res_type == RESOURCE_TYPES.WOOD \
                        and next_clust.has_no_units_no_enemy():
                    dist = next_clust.distance_to(cluster.get_centroid())
                    if dist < next_cluster_dist:
                        next_cluster_dist = dist
                        next_cluster = next_clust

            # find the closest unit of cluster to next cluster
            closest_unit_dist = math.inf
            closest_unit_to: Unit = None
            if next_cluster is not None:
                for unitid in cluster.units:
                    unit = player.units_by_id[unitid]
                    dist = unit.pos.distance_to(next_cluster.get_centroid())
                    if dist < closest_unit_dist and unit:
                        closest_unit_dist = dist
                        closest_unit_to = unit

            if closest_unit_to is not None:
                print(t_prefix, ' repurposing', closest_unit_to.id, ' to explore ', next_cluster.id, file=sys.stderr)
                unit_info[closest_unit_to.id].set_unit_role_explorer(next_cluster.get_centroid())

    # max number of units available
    units_cap = sum([len(x.citytiles) for x in player.cities.values()])

    unit_ceiling = int(min(float(units_cap), max(float(len(available_resources_tiles)) * 1.8, 5)))

    cities = list(player.cities.values())
    unsafe_cities = {}
    lowest_autonomy = 0
    available_city_actions = 0
    available_city_actions_now_and_next = 0;
    do_research_points = 0
    number_city_tiles = 0

    if len(cities) > 0:
        for city in cities:
            will_live = get_autonomy_turns(city) >= game_state_info.all_night_turns_lef
            # collect unsafe cities
            if not will_live:
                unsafe_cities[city.cityid] = (
                    len(city.citytiles),
                    (game_state_info.all_night_turns_lef - get_autonomy_turns(city)) * city.get_light_upkeep())

            # record how many research points we have now
            for city_tile in city.citytiles[::-1]:
                number_city_tiles = number_city_tiles + 1
                if city_tile.can_act():
                    available_city_actions += 1
                if city_tile.cooldown <= 1:
                    available_city_actions_now_and_next += 1

    # todo move print in  game_state_info class
    print(game_state.turn, 'resources', len(available_resources_tiles), 'units', units, 'unit_ceiling', unit_ceiling,
          'research', player.research_points, ' avail city points', available_city_actions, file=sys.stderr)

    if (not player.researched_uranium()) and player.research_points + available_city_actions >= 200:
        do_research_points = 200 - player.research_points
        print('We could complete uranium using', do_research_points, 'of', available_city_actions,
              file=sys.stderr)
    elif (not player.researched_coal()) and player.research_points + available_city_actions >= 50:
        do_research_points = 50 - player.research_points
        print('We could complete coal using', do_research_points, 'of', available_city_actions, file=sys.stderr)
    elif (not player.researched_uranium()) and player.research_points + available_city_actions >= 200:
        do_research_points = 200 - player.research_points
        print('We could complete NEXT uranium using', do_research_points, 'of',
              available_city_actions_now_and_next, file=sys.stderr)
    elif (not player.researched_coal()) and player.research_points + available_city_actions_now_and_next >= 50:
        do_research_points = 50 - player.research_points
        print('We could complete NEXT coal using', do_research_points, 'of', available_city_actions_now_and_next,
              file=sys.stderr)

    number_work_we_can_build = available_city_actions - do_research_points
    number_work_we_want_to_build = unit_ceiling - units

    if len(available_resources_tiles) == 0 and game_info.still_can_do_reseach():
        number_work_we_want_to_build = 0

    # last ten turn, just build in case it is a tie
    if game_state.turn > 350:
        number_work_we_want_to_build = number_work_we_can_build

    # Find how many and where to create builders

    print('number_work_we_can_build', number_work_we_can_build, 'number_work_we_want_to_build',
          number_work_we_want_to_build, file=sys.stderr)
    do_another_cycle = True
    while min(number_work_we_can_build, number_work_we_want_to_build) > 0 and do_another_cycle:
        do_another_cycle = False
        for city in reversed(cities):
            city_autonomy = get_autonomy_turns(city)
            will_live = city_autonomy >= game_state_info.all_night_turns_lef
            lowest_autonomy = min(lowest_autonomy, city_autonomy)
            for city_tile in city.citytiles[::-1]:
                # print("- C tile ", city_tile.pos, " CD=", city_tile.cooldown, file=sys.stderr)
                if city_tile.can_act():
                    if (not will_live) or len(unsafe_cities) == 0:
                        # let's create one more unit in the last created city tile if we can
                        actions.append(city_tile.build_worker())
                        print(city_tile.pos, "- created worker", file=sys.stderr)
                        number_work_we_can_build -= 1
                        number_work_we_want_to_build -= 1
                        do_another_cycle = True

    if len(cities) > 0:
        for city in reversed(cities):
            for city_tile in city.citytiles[::-1]:
                # print("- C tile ", city_tile.pos, " CD=", city_tile.cooldown, file=sys.stderr)
                if city_tile.can_act():
                    if game_info.still_can_do_reseach():
                        # let's do research
                        game_info.do_research(actions, city_tile, str(city_tile.pos) + " research")
                    # else:
                    # print("- - nothing", file=sys.stderr)

    print("Unsafe cities", unsafe_cities, file=sys.stderr)

    # trace the agent move
    # store all unit current location on move tracker
    for unit in player.units:
        if not unit.can_act():
            move_mapper.add_position(unit.pos, unit)

    # map of resource to unit going for them
    resource_target_by_unit = {}

    for unit in player.units:
        info: UnitInfo = unit_info[unit.id]
        prefix: str = "T_" + game_state.turn.__str__() + str(unit.id)

        print(prefix, ";pos", unit.pos, 'CD=', unit.cooldown, cargo_to_string(unit.cargo), 'fuel=',
              cargo_to_fuel(unit.cargo), 'canBuildHere', unit.can_build(game_state.map), 'role', info.role,
              file=sys.stderr)
        if (move_mapper.is_position_city(unit.pos) and 2 < game_state.turn < 15 and number_city_tiles == 1 and len(
                player.units) == 1):
            print(prefix, ' NEEDS to become an expander', file=sys.stderr)
            info.set_unit_role('expander', prefix)

        if unit.is_worker() and unit.can_act():
            adjacent_empty_tiles = find_all_adjacent_empty_tiles(game_state, unit.pos)
            closest_empty_tile = adjacent_empty_tile_favor_close_to_city(adjacent_empty_tiles, game_state, player)
            resources_distance = ResourceService.find_resources_distance(unit.pos, player, all_resources_tiles,
                                                                         game_info)

            print(prefix, 'adjacent_empty_tiles', [x.__str__() for x in adjacent_empty_tiles],
                  'favoured', closest_empty_tile.pos if closest_empty_tile else '', file=sys.stderr)

            #   EXPLORER
            if info.is_role_city_explorer():
                print(prefix, ' is explorer ', info.target_position, file=sys.stderr)
                if game_state_info.turns_to_night <= 2:
                    print(prefix, ' explorer failed as too close to night', file=sys.stderr)
                else:
                    # check if the target position is achievable
                    cluster = clusters.get_cluster_from_centroid(info.target_position)
                    if cluster is not None:
                        target_pos, distance = MapAnalysis.get_closest_position(
                            unit.pos,
                            cluster.exposed_perimeter
                        )
                        print(prefix, ' explorer is to cluster', cluster.id, file=sys.stderr)
                    else:
                        target_pos = info.target_position
                        distance = unit.pos.distance_to(info.target_position)

                    if distance <= (game_state_info.turns_to_night + 1) / 2:
                        print(prefix, ' explorer will go to', target_pos, 'dist', distance, file=sys.stderr)
                        info.set_unit_role_traveler(target_pos, 2 * distance)
                    else:
                        print(prefix, ' dist', distance, ' to ', target_pos, 'not compatible with autonomy',
                              file=sys.stderr)

                if info.is_role_city_explorer():
                    print(prefix, ' failed to find resource for explorer, clearing role', file=sys.stderr)
                    info.clean_unit_role()

            #   EXPANDER
            if info.is_role_city_expander() and unit.get_cargo_space_left() > 0:
                print(prefix, ' is expander', file=sys.stderr)

                # all action expander are based on building next turn. We don't build at last day, so skip if day before
                if game_state_info.turns_to_night > 1:
                    if is_position_adjacent_city(player, unit.pos) and (not move_mapper.is_position_city(unit.pos)) \
                            and ResourceService.is_position_adjacent_to_resource(wood_tiles, unit.pos):
                        # if we are next to city and to wood, just stay here
                        print(prefix, ' expander we are between city and wood do not move', file=sys.stderr)
                        continue

                    # if we have the possibility of going in a tile that is like the  above
                    expander_perfect_spot = empty_tile_near_wood_and_city(adjacent_empty_tiles, wood_tiles,
                                                                          game_state, player)
                    if expander_perfect_spot is not None:
                        if try_to_move_to(actions, move_mapper, info, expander_perfect_spot.pos,
                                          " expander to perfect pos"):
                            continue

            #   EXPANDER ENDS

            # night rules
            if game_state_info.is_night_time() or game_state_info.is_night_tomorrow():
                # time_to_dawn differs from game_state_info.turns_to_dawn as it could be even 11 on turn before night
                time_to_dawn = 10 + game_state_info.steps_until_night
                print(prefix, ' it is night...', 'time_to_dawn', time_to_dawn,
                      'inCity', move_mapper.is_position_city(unit.pos), 'empty', is_cell_empty(unit.pos, game_state)
                      , 'nearwood', ResourceService.is_position_adjacent_to_resource(wood_tiles, unit.pos),
                      file=sys.stderr)

                if ResourceService.is_position_adjacent_to_resource(wood_tiles, unit.pos) and is_cell_empty(unit.pos,
                                                                                                            game_state):
                    print(prefix, ' it is night, we are in a empty cell near resources', file=sys.stderr)
                    # empty near a resource, we can stay here, but we could even better go to same near city

                    # if we have the possibility of going in a tile that is like the  above
                    best_night_spot = empty_tile_near_wood_and_city(adjacent_empty_tiles, wood_tiles,
                                                                    game_state, player)
                    if best_night_spot is not None \
                            and try_to_move_to(actions, move_mapper, info, best_night_spot.pos, " best_night_spot"):
                        continue
                    else:
                        print(prefix, ' it is night, we will stay here', file=sys.stderr)
                        continue

                # if we have the possibility of going in a tile that is like the above,
                # go id not in a city, or if you are in a city, go just last 1 days of night (so we gather and covered)
                if (not move_mapper.is_position_city(unit.pos)) or time_to_dawn <= 1:
                    best_night_spot = empty_tile_near_wood_and_city(adjacent_empty_tiles, wood_tiles,
                                                                    game_state, player)
                    if best_night_spot is not None \
                            and try_to_move_to(actions, move_mapper, info, best_night_spot.pos, " best_night_spot"):
                        continue

                if game_state_info.is_night_time() and cargo_to_fuel(unit.cargo) > 0:
                    # if we have resources, next to a city that will die in this night,
                    # and we have enough resources to save it, then move
                    cities = adjacent_cities(player, unit.pos)
                    # order cities by decreasing size
                    cities = collections.OrderedDict(sorted(cities.items(), key=lambda x: x[-1]))
                    if len(cities) > 0:
                        is_any_city_in_danger = False
                        for city, city_payload in cities.items():
                            autonomy = city_payload[1]
                            if autonomy < time_to_dawn:
                                print(prefix, 'night, city in danger', city.cityid, 'sz/aut/dir', city_payload,
                                      file=sys.stderr)
                                is_any_city_in_danger = True
                                break

                        if is_any_city_in_danger:
                            # todo maybe we should choose a city that we can save by moving there?
                            print(prefix, 'try to save city', city.cityid, city_payload, file=sys.stderr)
                            move_unit_to(actions, city_payload[2], move_mapper, info, " try to save a city")
                            continue

                if move_mapper.is_position_city(unit.pos):
                    print(prefix, ' it is night, we are in city, do not move', file=sys.stderr)
                    continue

            # DAWN

            if game_state_info.is_dawn():
                print(prefix, "It's dawn", file=sys.stderr)
                if ResourceService.is_position_adjacent_to_resource(wood_tiles, unit.pos) and is_cell_empty(unit.pos,
                                                                                                            game_state) \
                        and 0 < unit.get_cargo_space_left() <= 21:
                    print(prefix, ' at dawn, can build next day', file=sys.stderr)
                    continue

            #   TRAVELER
            if info.is_role_traveler():
                print(prefix, ' is traveler to', info.target_position, file=sys.stderr)
                direction = get_direction_to_quick(game_state, unit, info.target_position, move_mapper)
                if direction != DIRECTIONS.CENTER and move_mapper.can_move_to_direction(info.unit.pos, direction):
                    move_unit_to(actions, direction, move_mapper, info, " move to traveler pos", info.target_position)
                    continue
                else:
                    print(prefix, ' traveller cannot move', file=sys.stderr)
                    if unit.pos.distance_to(info.target_position) <= 1:
                        info.clean_unit_role()

            #   RETURNER
            if info.is_role_returner():
                print(prefix, ' is returner to', info.target_position, file=sys.stderr)
                direction = get_direction_to_quick(game_state, unit, info.target_position, move_mapper, True)
                move_unit_to_or_transfer(actions, direction, info, move_mapper, player, prefix, unit, 'returner')

            #   HASSLER
            if info.is_role_hassler():
                print(prefix, ' is hassler', file=sys.stderr)
                if is_position_adjacent_city(opponent, unit.pos):
                    print(prefix, ' hassler arrived to enemy', file=sys.stderr)
                    if unit.can_build(game_state.map):
                        build_city(actions, info, 'hassler build next to city, and done!')
                        info.clean_unit_role()
                        continue
                    elif unit.get_cargo_space_left() == 0 and closest_empty_tile is not None:

                        print(prefix, " hassler full and close to empty, trying to move and build",
                              closest_empty_tile.pos, file=sys.stderr)
                        direction = unit.pos.direction_to(closest_empty_tile.pos)
                        next_pos = unit.pos.translate(direction, 1)
                        move_unit_to(actions, direction, move_mapper, info,
                                     " move to build nearby enemy",
                                     next_pos)
                        continue

                else:
                    enemy_surrounding = find_closest_adjacent_enemy_city_tile(unit.pos, opponent)
                    direction = unit.pos.direction_to(enemy_surrounding.pos)
                    # if nobody is already moving there
                    if not move_mapper.has_position(enemy_surrounding.pos):
                        move_unit_to(actions, direction, move_mapper, info, " move to enemy", enemy_surrounding.pos)
                        continue

                continue
            #   HASSLER ENDS

            # if unit cant make city tiles try to collect resource collection.
            city_tile_distance = find_city_tile_distance(unit.pos, player, unsafe_cities)

            # build city tiles adjacent of other tiles to make only one city.
            if unit.can_build(game_state.map):
                if is_position_adjacent_city(player, unit.pos):
                    build_city(actions, info, 'in adjacent city!')
                    continue
                else:
                    # if we can move to a tile where we are adjacent, do and it and build there
                    if closest_empty_tile is not None:
                        print(prefix, " check if adjacent empty is more interesting", closest_empty_tile.pos,
                              file=sys.stderr)
                        direction = unit.pos.direction_to(closest_empty_tile.pos)
                        next_pos = unit.pos.translate(direction, 1)
                        # if nobody is already moving there
                        if not move_mapper.has_position(next_pos):
                            print(prefix, " and nobody is moving here", file=sys.stderr)
                            # and if next pos is actually adjacent
                            if is_position_adjacent_city(player, next_pos):
                                move_unit_to(actions, direction, move_mapper, info,
                                             " we could have build here, but we move close to city instead", next_pos)
                                continue

                if game_state_info.turns_to_night > 1 or \
                        (game_state_info.turns_to_night == 1
                        and ResourceService.is_position_adjacent_to_resource(available_resources_tiles,unit.pos)):
                    unit_fuel=cargo_to_fuel(unit.cargo)
                    if unit_fuel< 200:
                        build_city(actions, info, 'NOT in adjacent city, we have not so much fuel '+str(unit_fuel))
                        continue
                    else:
                        do_build=True
                        # check if there are cities next to us that are better served with our fuel
                        for city_tile, dist in city_tile_distance.items():
                            distance = dist[0]
                            autonomy = dist[1]
                            city_size = abs(dist[2])
                            if city_size>=5 and distance<6:
                                do_build=False
                                break

                        if do_build:
                            build_city(actions, info, 'NOT in adjacent city, we have lot of fuel, but no city needs saving')
                            continue
                        else:
                            print(prefix, " we could have built NOT in adjacent city, but there is a need city close"
                                  , city_tile.cityid,file=sys.stderr)

            if game_state_info.is_night_time():
                enough_fuel = 500
            elif game_state_info.turns_to_night < 4:
                enough_fuel = 300
            else:
                enough_fuel = 400

            if (not info.is_role_returner()) and unit.get_cargo_space_left() > 0 \
                    and (cargo_to_fuel(unit.cargo) < enough_fuel or len(unsafe_cities) == 0 or info.is_role_hassler()):
                if not ResourceService.is_position_resource(available_resources_tiles, unit.pos):
                    # find the closest resource if it exists to this unit

                    print(prefix, " Find resources", file=sys.stderr)

                    if resources_distance is not None and len(resources_distance) > 0:
                        # create a move action to the direction of the closest resource tile and add to our actions list
                        direction, pos, msg, resource_type = find_best_resource(game_state, move_mapper,
                                                                                resources_distance,
                                                                                resource_target_by_unit, unit, prefix)
                        if (resource_type == RESOURCE_TYPES.COAL and not player.researched_coal()) or \
                                (resource_type == RESOURCE_TYPES.URANIUM and not player.researched_uranium()):
                            # this is a not researched yet resource, force to go there, so there is no jitter
                            distance_to_res = pos.distance_to(unit.pos)
                            print(prefix, " Found resource not yet researched:", resource_type, "dist", distance_to_res,
                                  file=sys.stderr)
                            info.set_unit_role_traveler(pos, 2 * distance_to_res, prefix)

                        if pos is not None:
                            # append target to our map
                            resource_target_by_unit.setdefault((pos.x, pos.y), []).append(unit.id)
                        move_unit_to(actions, direction, move_mapper, info, msg, pos)
                        continue
                    else:
                        print(prefix, " resources_distance invalid (or empty?)", file=sys.stderr)
                else:
                    resource_type = game_state.map.get_cell(unit.pos.x, unit.pos.y).resource.type
                    print(prefix, " Already on resources:", resource_type, file=sys.stderr)
                    if resource_type != RESOURCE_TYPES.WOOD \
                            and get_friendly_unit(player, info.last_move_before_pos) is not None and \
                            move_mapper.can_move_to_direction(unit.pos, info.last_move_direction):
                        move_unit_to(actions, info.last_move_direction, move_mapper, info, 'move a bit further')
                    else:
                        resource_target_by_unit.setdefault((unit.pos.x, unit.pos.y), []).append(unit.id)
                        print(prefix, " Stay on resources", file=sys.stderr)
                    continue
            else:
                if game_state_info.turns_to_night > 10 and unit.get_cargo_space_left() <= 40 \
                        and ResourceService.is_position_resource(available_resources_tiles, unit.pos) \
                        and closest_empty_tile is not None:
                    # if we are on a resource, and we can move to an empty tile,
                    # then it means we can at least collect 20 next turn on CD and then build
                    # find the closest empty tile it to build a city
                    direction = unit.pos.direction_to(closest_empty_tile.pos)
                    move_unit_to(actions, direction, move_mapper, info,
                                 " towards closest empty (anticipating getting resources)", closest_empty_tile.pos)
                elif game_state_info.turns_to_night > 10 and unit.get_cargo_space_left() == 0 \
                        and closest_empty_tile is not None:
                    # find the closest empty tile it to build a city
                    direction = unit.pos.direction_to(closest_empty_tile.pos)
                    move_unit_to(actions, direction, move_mapper, info, " towards closest empty ",
                                 closest_empty_tile.pos)
                else:
                    print(prefix, " Goto city; fuel=",cargo_to_fuel(unit.cargo), file=sys.stderr)
                    # find closest city tile and move towards it to drop resources to a it to fuel the city
                    if city_tile_distance is not None and len(city_tile_distance) > 0 and not info.is_role_hassler():
                        print(prefix, " Goto city2", file=sys.stderr)
                        direction, pos, msg = find_best_city(game_state, city_tile_distance, move_mapper, unsafe_cities, unit)
                        move_unit_to_or_transfer(actions, direction, info, move_mapper, player, prefix, unit, 'city')

    # if this unit didn't do any action, check if we can transfer his cargo back in the direction this come from
    for unit in player.units:
        info: UnitInfo = unit_info[unit.id]
        prefix: str = "T_" + game_state.turn.__str__() + str(unit.id)
        # print(prefix, "XXX check unit has worked", unit.can_act(), info.has_done_action_this_turn,file=sys.stderr)
        if unit.is_worker() and unit.can_act() and not info.has_done_action_this_turn:
            print(prefix, " this unit has not worked", file=sys.stderr)
            if unit.cargo.coal > 0 or unit.cargo.uranium > 0:
                # check if anybody in the pos where we come from
                friend_unit = get_friendly_unit(player, info.last_move_before_pos)
                if friend_unit is not None:
                    print(prefix, " Do transfer to", friend_unit.id, ' in ', info.last_move_before_pos,
                          file=sys.stderr)
                    transfer_all_resources(actions, info, friend_unit.id)
                    if unit_info[unit.id].is_role_traveler:
                        unit_info[unit.id].clean_unit_role();

    # for i,j in resource_target_by_unit.items():
    #    print("XXXX resources map ",game_info.turn,i,len(j), file=sys.stderr)

    return actions


def move_unit_to_or_transfer(actions, direction, info, move_mapper, player, prefix, unit, msg):
    if direction != DIRECTIONS.CENTER and move_mapper.can_move_to_direction(info.unit.pos, direction):
        move_unit_to(actions, direction, move_mapper, info, " move to " + msg + " pos", info.target_position)
        # continue
    else:
        # check if anybody in the pos we want to go
        friend_unit = get_friendly_unit(player, unit.pos.translate(direction, 1))
        if friend_unit is not None \
                and friend_unit.get_cargo_space_left() > 100 - unit.get_cargo_space_left():
            print(prefix, msg, "instead of going to city, do transfer to", friend_unit.id,
                  ' in ', unit.pos.translate(direction, 1), file=sys.stderr)
            transfer_all_resources(actions, info, friend_unit.id)
            if unit_info[unit.id].is_role_traveler() or unit_info[unit.id].is_role_returner():
                unit_info[unit.id].clean_unit_role()
            if unit_info[friend_unit.id].is_role_traveler():
                unit_info[friend_unit.id].clean_unit_role()
        else:
            direction = get_random_step(unit.pos, move_mapper)
            move_unit_to(actions, direction, move_mapper, info, "randomly (due to " + msg + ")")
            # continue


def get_friendly_unit(player, pos) -> Unit:
    for unit in player.units:
        if unit.pos.equals(pos):
            return unit

    return None


def find_best_city(game_state, city_tile_distance, move_mapper: MoveHelper, unsafe_cities, unit) -> Tuple[
    DIRECTIONS, Optional[Position], str]:
    closest_city_tile = None
    moved = False
    for city_tile, dist in city_tile_distance.items():
        if not move_mapper.has_position(city_tile.pos):
            closest_city_tile = city_tile
            if closest_city_tile is not None:
                direction = get_direction_to_city(game_state, unit, closest_city_tile.pos, unsafe_cities, move_mapper, True)
                if direction != DIRECTIONS.CENTER:
                    moved = True
                    return direction, closest_city_tile.pos, " towards closest city distancing and autonomy, size" + dist.__str__()

    if not moved:
        direction = get_random_step(unit.pos, move_mapper)
        return direction, None, "randomly (due to city)"


def find_best_resource(game_state, move_mapper: MoveHelper, resources_distance, resource_target_by_unit, unit,
                       prefix) -> \
        Tuple[DIRECTIONS, Optional[Position], str, str]:
    closest_resource_tile, c_dist = None, None
    moved = False
    # print(prefix, " XXX Find resources dis", resources_distance.values(), file=sys.stderr)
    # print(prefix, " XXX Find resources pos", resources_distance.keys(), file=sys.stderr)
    # print(prefix, " XXX Move mapper", move_mapper.move_mapper.keys(), file=sys.stderr)

    # we try not to allocate x units to same resource, but we are happy to go up to y in range (x,y)
    for max_units_per_resource in range(6, 7):
        for resource, resource_dist_info in resources_distance.items():
            # print(prefix, " XXX - ", resource.pos, resource_dist_info, file=sys.stderr)
            if resource is not None and not resource.pos.equals(unit.pos):
                if len(resource_target_by_unit.setdefault((resource.pos.x, resource.pos.y),
                                                          [])) < max_units_per_resource:
                    direction = get_direction_to_quick(game_state, unit, resource.pos, move_mapper, False)
                    if direction != DIRECTIONS.CENTER:
                        return direction, resource.pos, " towards closest resource ", resource_dist_info[2]

    direction = get_random_step(unit.pos, move_mapper)
    return direction, None, "randomly (due to resource)", ""


def get_autonomy_turns(city) -> int:
    turns_city_can_live = city.fuel // city.get_light_upkeep()
    return turns_city_can_live


def build_city(actions, info: UnitInfo, msg=''):
    actions.append(info.unit.build_city())
    print("Unit", info.unit.id, '- build city', msg, file=sys.stderr)
    info.set_last_action_build()


def transfer_all_resources(actions, info: UnitInfo, to_unit_id):
    if info.unit.cargo.uranium > 0:
        actions.append(info.unit.transfer(to_unit_id, RESOURCE_TYPES.URANIUM, info.unit.cargo.uranium))
        print("Unit", info.unit.id, '- transfer', info.unit.cargo.uranium, 'uranium to ', to_unit_id, file=sys.stderr)
        info.set_last_action_transfer()
    elif info.unit.cargo.coal > 0:
        actions.append(info.unit.transfer(to_unit_id, RESOURCE_TYPES.COAL, info.unit.cargo.coal))
        print("Unit", info.unit.id, '- transfer', info.unit.cargo.coal, 'coal to ', to_unit_id, file=sys.stderr)
        info.set_last_action_transfer()
    elif info.unit.cargo.wood > 0:
        actions.append(info.unit.transfer(to_unit_id, RESOURCE_TYPES.WOOD, info.unit.cargo.wood))
        print("Unit", info.unit.id, '- transfer', info.unit.cargo.wood, 'wood to ', to_unit_id, file=sys.stderr)
        info.set_last_action_transfer()


def can_city_live(city, all_night_turns_lef) -> bool:
    return city.fuel / (city.get_light_upkeep() + 20) >= min(all_night_turns_lef, 30)


def move_unit_to(actions, direction, move_mapper: MoveHelper, info: UnitInfo, reason="", target_far_position=None):
    unit = info.unit
    next_state_pos = unit.pos.translate(direction, 1)
    # print("Unit", unit.id, 'XXX -', unit.pos, next_state_pos, direction, file=sys.stderr)
    if direction == DIRECTIONS.CENTER or next_state_pos.equals(unit.pos):
        # do not annotate
        print(move_mapper.log_prefix, unit.id, '- not moving "', '', '" ', reason, file=sys.stderr)
        move_mapper.add_position(unit.pos, unit)
    else:
        if target_far_position is not None:
            # target_far_position is only used for the annotation line
            actions.append(annotate.line(unit.pos.x, unit.pos.y, target_far_position.x, target_far_position.y))
            # actions.append(annotate.text(unit.pos.x, unit.pos.y, reason))

        actions.append(unit.move(direction))
        move_mapper.add_position(next_state_pos, unit)
        info.set_last_action_move(direction)
        print(move_mapper.log_prefix, unit.id, '- moving towards "', direction, next_state_pos, '" :', reason
              , str(target_far_position or ''), file=sys.stderr)


def is_position_adjacent_city(player, pos, do_log=False) -> bool:
    for city in player.cities.values():
        for city_tile in city.citytiles:
            if city_tile.pos.is_adjacent(pos):
                if do_log:
                    print(pos, "is_position_adjacent_city", city_tile.pos, file=sys.stderr)
                return True

    return False


def try_to_move_to(actions, move_mapper, info: UnitInfo, pos: Position, msg: str) -> bool:
    direction = info.unit.pos.direction_to(pos)
    # if nobody is already moving there
    if not move_mapper.has_position(pos):
        move_unit_to(actions, direction, move_mapper, info, msg, pos)
        return True
    else:
        return False


def get_resources_around(resource_tiles: List[Cell], pos: Position, max_dist) -> List[Cell]:
    resources = []
    for r in resource_tiles:
        if pos.distance_to(r.pos) <= max_dist:
            resources.append(r)

    return resources


# return dist of cities, autonomy
def adjacent_cities(player, pos: Position, do_log=False) -> {City, Tuple[int, int, DIRECTIONS]}:
    cities = {}
    for city in player.cities.values():
        for city_tile in city.citytiles:
            if city_tile.pos.is_adjacent(pos):
                if do_log:
                    print(pos, "adjacent_cities", city_tile.pos, file=sys.stderr)
                cities[city] = (len(city.citytiles), get_autonomy_turns(city), directions_to(pos, city_tile.pos)[0])

    return cities


def get_direction_to_quick(game_state: Game, unit: Unit, target_pos: Position, move_mapper: MoveHelper,
                           allow_clash_unit: bool = False) -> DIRECTIONS:
    # below to turn smart direction on for all resources and city trip
    # return get_direction_to_smart(game_state,unit, target_pos, move_mapper)

    from_pos = unit.pos
    if from_pos.equals(target_pos):
        return DIRECTIONS.CENTER

    directions = directions_to(from_pos, target_pos)
    for direction in directions:
        next_pos = from_pos.translate(direction, 1)

        # if we are trying to move on top of somebody else, skip
        # print(' XXX - try', direction, next_pos,'mapper', move_mapper.move_mapper.keys(),file=sys.stderr)
        if move_mapper.can_move_to_pos(next_pos, allow_clash_unit, unit.id + ' moving to ' + direction):
            return direction
        else:
            # print(' XXX - skip', file=sys.stderr)
            continue

    return DIRECTIONS.CENTER

#as get_direction_to_quick, but avoid other cities
def get_direction_to_city(game_state: Game, unit: Unit, target_pos: Position, unsafe_cities,
                          move_mapper: MoveHelper,
                           allow_clash_unit: bool = False) -> DIRECTIONS:
    # below to turn smart direction on for all resources and city trip
    # return get_direction_to_smart(game_state,unit, target_pos, move_mapper)

    from_pos = unit.pos
    if from_pos.equals(target_pos):
        return DIRECTIONS.CENTER

    directions = directions_to(from_pos, target_pos)
    for direction in directions:
        next_pos = from_pos.translate(direction, 1)
        if move_mapper.is_position_city(next_pos):
            city_on_the_way = move_mapper.get_city_id_from_pos(next_pos, move_mapper.player)
            if city_on_the_way not in unsafe_cities:
                # this is a safe city, but not the one where we want to reach
                print(' XXX - skip ', direction, next_pos, 'as it goes to safe city',city_on_the_way, file=sys.stderr)
                continue

        # if we are trying to move on top of somebody else, skip
        # print(' XXX - try', direction, next_pos,'mapper', move_mapper.move_mapper.keys(),file=sys.stderr)
        if move_mapper.can_move_to_pos(next_pos, allow_clash_unit, unit.id + ' moving to ' + direction):
            return direction
        else:
            # print(' XXX - skip', file=sys.stderr)
            continue

    return DIRECTIONS.CENTER

def get_direction_to_smart_XXX(game_state: Game, unit: Unit, target_pos: Position,
                               move_mapper: MoveHelper) -> DIRECTIONS:
    smallest_cost = [2, 2, 2, 2]
    closest_dir = DIRECTIONS.CENTER
    closest_pos = unit.pos

    for direction in game_state.dirs:
        newpos = unit.pos.translate(direction, 1)

        cost = [0, 0, 0, 0]

        # do not go out of map
        if tuple(newpos) in game_state.xy_out_of_map:
            continue

        # discourage if new position is occupied
        if tuple(newpos) in game_state.occupied_xy_set:
            if tuple(newpos) not in game_state.player_city_tile_xy_set:
                cost[0] = 2

        # discourage going into a city tile if you are carrying substantial wood
        if tuple(newpos) in game_state.player_city_tile_xy_set and unit.cargo.wood >= 60:
            cost[0] = 1

        # path distance as main differentiator
        path_dist = game_state.retrieve_distance(newpos.x, newpos.y, target_pos.x, target_pos.y)
        cost[1] = path_dist

        # manhattan distance to tie break
        manhattan_dist = (newpos - target_pos)
        cost[2] = manhattan_dist

        # prefer to walk on tiles with resources
        aux_cost = game_state.convolved_collectable_tiles_matrix[newpos.y, newpos.x]
        cost[3] = -aux_cost

        # if starting from the city, consider manhattan distance instead of path distance
        if tuple(unit.pos) in game_state.player_city_tile_xy_set:
            cost[1] = manhattan_dist

        # update decision
        if cost < smallest_cost:
            smallest_cost = cost
            closest_dir = direction
            closest_pos = newpos

    if closest_dir != DIRECTIONS.CENTER:
        game_state.occupied_xy_set.discard(tuple(unit.pos))
        if tuple(closest_pos) not in game_state.player_city_tile_xy_set:
            game_state.occupied_xy_set.add(tuple(closest_pos))
        unit.cooldown += 2

    return closest_dir