from lux.game_map import Position, RESOURCE_TYPES
from lux.game_objects import Unit, Cargo
import sys
from LazyWrapper import LazyWrapper as Lazy

class UnitInfo:
    def __init__(self, unit: Unit, pr):
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
        self.pr = pr
        self.transferred_in_cargo = Cargo()
        self.pr(self.log_prefix, 'created')
        self.cargo = Lazy(lambda: self._cargo())

    def update(self, unit: Unit, current_turn):
        self.unit = unit
        # update position
        self.previous_pos = self.current_pos
        self.current_pos = unit.pos
        self.has_done_action_this_turn = False
        self.current_turn = current_turn
        self.transferred_in_cargo = Cargo()
        self.cargo = Lazy(lambda: self._cargo())

        #
        self.gathered_last_turn = unit.get_cargo_space_left() - self.last_free_cargo
        self.last_free_cargo = unit.get_cargo_space_left()
        u_prefix: str = "T_" + current_turn.__str__() + str(unit.id)

        if self.last_move_expected_pos is not None and self.last_move_turn == current_turn - 1:
            if not unit.pos.equals(self.last_move_expected_pos):
                self.pr(u_prefix, 'this unit has not moved as expected to', self.last_move_expected_pos)
                self.alarm += 1
            else:
                self.alarm = 0

        if self.role_time_turn_limit > 0:
            self.role_time_turn_limit -= 1
            if self.role_time_turn_limit == 0:
                self.clean_unit_role('time turn reached', u_prefix)

        if self.is_role_returner() and self.unit.get_cargo_space_left() == 100:
            self.clean_unit_role('returner has now not anymore cargo', u_prefix)

        if self.target_position is not None:
            if unit.pos.equals(self.target_position):
                self.clean_unit_role('reached target position' + self.target_position.__str__(), u_prefix)

    def _cargo(self) -> Cargo:
        if self.transferred_in_cargo is not None:
            return self.transferred_in_cargo + self.unit.cargo
        else:
            return self.unit.cargo

    def add_cargo(self, res, qty):
        if res == RESOURCE_TYPES.WOOD:
            self.transferred_in_cargo.wood += qty
        elif res == RESOURCE_TYPES.COAL:
            self.transferred_in_cargo.coal += qty
        elif res == RESOURCE_TYPES.URANIUM:
            self.transferred_in_cargo.uranium += qty

    def get_cargo_space_used(self) -> int:
        return self.cargo().get_space_used()

    def get_cargo_space_left(self) -> int:
        return 100 - self.cargo().get_space_used()

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

    def set_unit_role_traveler(self, pos: Position, number_turns, prefix: str = '', msg: str = ''):
        if prefix == '':
            prefix = self.log_prefix
        self.pr(prefix, 'set unit', self.unit.id, 'as traveler to', pos, " for number_turns", number_turns, msg)
        self.set_unit_role('traveler', prefix)
        self.target_position = pos
        self.role_time_turn_limit = number_turns

    def set_unit_role_returner(self, prefix: str = ''):
        self.pr(self.log_prefix, 'set unit', self.unit.id, ' as returner')
        self.set_unit_role('returner', prefix)

    def set_unit_role_explorer(self, pos: Position, prefix: str = ''):
        if pos is not None:
            self.pr(self.log_prefix, 'set unit', self.unit.id, 'as explorer to', pos)
            self.set_unit_role('explorer', prefix)
            self.target_position = pos

    def set_unit_role_expander(self, prefix: str = ''):
        if prefix == '':
            prefix = self.log_prefix
        self.pr(prefix, 'set unit', self.unit.id, 'as expander')
        self.set_unit_role('expander', prefix)

    def set_unit_role(self, role, prefix: str = ''):
        self.role = role
        self.pr(prefix, "Setting unit", self.id, " as ", self.role)

    def clean_unit_role(self, msg='', prefix=''):
        if prefix == '':
            prefix = self.log_prefix
        if self.role != '':
            self.pr(prefix, 'removing role', self.role, msg)
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

    def __repr__(self):
        return "Info(" + self.unit.id + ")"
