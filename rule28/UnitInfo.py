from lux.game_map import Position
from lux.game_objects import Unit
import sys


class UnitInfo:
    def __init__(self, unit: Unit):
        """
        initialize state
        """
        self.id = unit.id
        self.unit = unit
        self.last_action = ''
        self.last_move = ''
        self.last_move_direction = ''
        self.last_move_turn = 0
        self.current_turn = 0
        self.has_mission = False
        self.previous_pos = None
        self.gathered_last_turn = 0
        self.last_free_cargo = unit.get_cargo_space_left()
        self.current_pos = unit.pos
        self.role = ''
        self.log_prefix = 'Unit_info ' + self.id
        self.target_position = None
        self.role_time_turn_limit = 0
        self.build_if_you_can = False
        self.has_done_action_this_turn = False
        self.last_move_before_pos = unit.pos
        self.last_move_expected_pos = None
        self.alarm = 0
        print(self.log_prefix, 'created', file=sys.stderr)

    def update(self, unit: Unit, current_turn):
        self.unit = unit
        # update position
        self.previous_pos = self.current_pos
        self.current_pos = unit.pos
        self.has_done_action_this_turn = False
        self.current_turn = current_turn
        #
        self.gathered_last_turn = unit.get_cargo_space_left() - self.last_free_cargo
        self.last_free_cargo = unit.get_cargo_space_left()

        if self.last_move_expected_pos is not None and self.last_move_turn == current_turn-1:
            if not unit.pos.equals(self.last_move_expected_pos):
                self.alarm +=1
            else:
                self.alarm = 0

        if self.role_time_turn_limit > 0:
            self.role_time_turn_limit -= 1
            if self.role_time_turn_limit == 0:
                self.clean_unit_role('time turn reached')

        if self.is_role_returner() and self.unit.get_cargo_space_left() == 100:
            self.clean_unit_role('returner has now not anymore cargo')

        if self.target_position is not None:
            if unit.pos.equals(self.target_position):
                self.clean_unit_role('reached target position'+self.target_position.__str__())

    def set_last_action_move(self, direction, to_pos):
        self.last_move = 'm'
        self.last_move_direction = direction
        self.last_move_turn = self.current_turn
        self.last_move_before_pos = self.unit.pos
        self.last_move_expected_pos = to_pos
        self.has_done_action_this_turn = True

    def set_last_action_build(self):
        self.last_move = 'b'
        self.has_done_action_this_turn = True

    def set_last_action_transfer(self):
        self.last_move = 't'
        self.has_done_action_this_turn = True

    def set_unit_role_traveler(self, pos: Position, number_turns):
        print(self.log_prefix, 'set this unit as traveler to', pos, " for number_turns", number_turns, file=sys.stderr)
        self.set_unit_role('traveler', self.log_prefix)
        self.target_position = pos
        self.role_time_turn_limit = number_turns

    def set_unit_role_returner(self, prefix: str = ''):
        print(self.log_prefix, 'set this unit as returner', file=sys.stderr)
        self.set_unit_role('returner', prefix)

    def set_unit_role_explorer(self, pos: Position, prefix: str = ''):
        if pos is not None:
            print(self.log_prefix, 'set this unit as explorer to', pos, file=sys.stderr)
            self.set_unit_role('explorer', prefix)
            self.target_position = pos

    def set_unit_role(self, role, prefix: str = ''):
        self.role = role
        print(prefix, "Setting unit", self.id, " as ", self.role, file=sys.stderr)

    def clean_unit_role(self, msg=''):
        if self.role != '':
            print(self.log_prefix, 'removing role', self.role,msg, file=sys.stderr)
        self.role = ''
        self.target_position = None
        self.build_if_you_can = False
        self.role_time_turn_limit = 0

    def is_role_none(self):
        return self.role == ''

    def is_role_city_expander(self):
        return self.role == 'expander'

    def is_role_explorer(self):
        return self.role == 'explorer'

    def is_role_hassler(self):
        return self.role == 'hassler'

    def is_role_traveler(self):
        return self.role == 'traveler'

    def is_role_returner(self):
        return self.role == 'returner'

    def set_build_if_you_can(self):
        self.build_if_you_can = True