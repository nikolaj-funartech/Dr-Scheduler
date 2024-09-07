import datetime
from datetime import date, timedelta
from typing import Dict, List, Any, Tuple
from collections import defaultdict
from ics import Calendar as IcsCalendar, Event
import json
import logging
from models.task import TaskType, TaskDaysParameter, Task

from ortools.sat.python import cp_model

logging.basicConfig(level=logging.DEBUG)

# models/math_schedule.py


class MathTask:
    """
    This class represents a mathematical task that is the basic unit in the mathematical model.

    A mathematical task is one contiguous time interval that corresponds to one `Task`. It can be
    spanning one day or several days, be contained in one week or overlapping over several weeks.
    As a continguous time interval, i.e. there is no whole in it, it has a start_date and an
    end_date and all the dates in between. If a `Task` corresponds to several day intervals,
    we create several corresponding `MathTask`s.
    """

    def __init__(self, name, task_type, y_vars, index, week_start, days, start_date, end_date, number_of_weeks, available_physicians, heaviness, mandatory):
        self.name = name
        assert isinstance(task_type, TaskType)
        self.task_type = task_type,
        self.y_vars = y_vars
        self.index = index
        self.week_start = week_start
        self.days = days  # to keep the current code as is and retrieve all days, list of days
        assert start_date == days[0]
        self.start_date = start_date
        assert end_date == days[-1]
        self.end_date = end_date
        self.number_of_weeks = number_of_weeks
        self.available_physicians = available_physicians
        self.heaviness = heaviness
        self.mandatory = mandatory

    def y_var(self, physician):
        """
        Return the variable for the given physician.

        Warnings:
            It does not matter if this physician is available or not.

        Args:
            physician (str):

        Returns:
            The corresponding mathematical variable.
        """
        return self.y_vars[(self.name, self.start_date, self.end_date, physician)]

    def is_physician_available(self, physician):
        """
        Returns if physician is available or not.

        Args:
            physician:

        Returns:
            True if physician is available, False otherwise.
        """
        return physician in self.available_physicians

    def __str__(self):
        return f"{self.name} [{self.start_date}, {self.end_date}]"

    def __repr__(self):
        return str(self)


class TaskMatcher:
    def __init__(self, physician_manager, task_manager):
        self.physician_manager = physician_manager
        self.task_manager = task_manager
        self.physician_task_counts = defaultdict(lambda: defaultdict(int))
        self.physician_task_days = defaultdict(lambda: defaultdict(list))
        self.physician_call_counts = defaultdict(lambda: defaultdict(int))
        self.last_heavy_task = {}
        self.revenue_distribution = defaultdict(float)

    def _is_physician_eligible(self, physician: str, task: Any, period: Dict[str, Any]) -> bool:
        physician_obj = self.physician_manager.get_physician_by_name(physician)
        logging.debug(f"Checking eligibility for physician {physician} for task {task.name}")

        if task.name in physician_obj.restricted_tasks or task.name in physician_obj.exclusion_tasks:
            logging.debug(f"Physician {physician} is restricted or excluded from task {task.name}")
            return False

        if task.is_call_task and self.physician_call_counts[physician][period['month']] > 0:
            logging.debug(f"Physician {physician} has already been assigned a call task in month {period['month']}")
            return False

        if task.is_discontinuous and not physician_obj.discontinuity_preference:
            logging.debug(f"Physician {physician} does not prefer discontinuous tasks")
            return False

        logging.debug(f"Physician {physician} is eligible for task {task.name}")
        return True

    def _get_eligible_physicians(self, available_physicians: List[str], task: Any, period: Dict[str, Any]) -> List[str]:
        return [
            p for p in available_physicians
            if self._is_physician_eligible(p, task, period)
        ]
    def _get_available_physicians(self, days: List[date]) -> List[str]:
        available_physicians = [
            physician.name
            for physician in self.physician_manager.data['physicians']
            if all(not self.physician_manager.is_unavailable(physician.name, day) for day in days)
        ]
        logging.debug(f"Available physicians for days {days}: {available_physicians}")
        return available_physicians

    def find_best_match(self, available_physicians: List[str], task: Any, period: Dict[str, Any], month: int) -> Tuple[str, float]:
        logging.debug(f"Finding best match for task {task.name} in period {period} for month {month}")
        eligible_physicians = self._get_eligible_physicians(available_physicians, task, period)

        if not eligible_physicians:
            logging.debug(f"No eligible physicians found for task {task.name}")
            return None, 0

        scored_physicians = self._score_physicians(eligible_physicians, task, period, month)
        best_physician = max(scored_physicians, key=scored_physicians.get)
        logging.debug(f"Best match for task {task.name} is physician {best_physician} with score {scored_physicians[best_physician]}")
        return best_physician, scored_physicians[best_physician]

    def _score_physicians(self, eligible_physicians: List[str], task: Any, period: Dict[str, Any], month: int) -> Dict[
        str, float]:
        scores = {}
        for physician in eligible_physicians:
            physician_obj = self.physician_manager.get_physician_by_name(physician)
            score = 0
            score += self._score_preference(physician_obj, task)
            score += self._score_fairness(physician, task)
            score += self._score_call_distribution(physician, task, month)
            score += self._score_heavy_task_avoidance(physician, task, period)
            score += self._score_discontinuity_preference(physician_obj, task)
            score += self._score_desired_working_weeks(physician)
            score += self._score_revenue_distribution(physician)
            score += self._score_consecutive_category_avoidance(physician, task)
            scores[physician] = score
        return scores

    def _score_consecutive_category_avoidance(self, physician: str, task: Any) -> float:
        last_task = self.physician_task_counts[physician].get('last_task')
        if last_task and last_task.category == task.category and task.number_of_weeks <= 1:
            return -10
        return 0

    def _score_preference(self, physician_obj: Any, task: Any) -> float:
        return 10 if task.name in physician_obj.preferred_tasks else 0

    def _score_fairness(self, physician: str, task: Any) -> float:
        task_count = self.physician_task_counts[physician][task.name]
        return 5 / (task_count + 1)

    def _score_call_distribution(self, physician: str, task: Any, month: int) -> float:
        if task.is_call_task:
            call_count = self.physician_call_counts[physician][month]
            return 5 / (call_count + 1)
        return 0

    def _score_heavy_task_avoidance(self, physician: str, task: Any, period: Dict[str, Any]) -> float:
        if task.is_heavy:
            if physician not in self.last_heavy_task or \
                    (period['days'][0] - self.last_heavy_task[physician]).days > 7:
                return 5
        return 0

    def _score_discontinuity_preference(self, physician_obj: Any, task: Any) -> float:
        if task.is_discontinuous:
            return 10 if physician_obj.discontinuity_preference else -5
        return 0

    def _score_desired_working_weeks(self, physician: str) -> float:
        total_days = sum(len(days) for days in self.physician_task_days[physician].values())
        physician_obj = self.physician_manager.get_physician_by_name(physician)
        if total_days / 7 < physician_obj.desired_working_weeks * 52:
            return 5
        return 0

    def _score_revenue_distribution(self, physician: str) -> float:
        if not self.revenue_distribution:
            return 0
        avg_revenue = sum(self.revenue_distribution.values()) / len(self.revenue_distribution)
        if self.revenue_distribution[physician] < avg_revenue:
            return 5
        return 0

    def update_physician_stats(self, physician: str, task: Any, period: Dict[str, Any]):
        self.physician_task_counts[physician][task] += 1
        self.physician_task_days[physician][task].extend(period['days'])

        if task.is_call_task:
            self.physician_call_counts[physician][period['days'][0].month] += 1

        if task.is_heavy:
            self.last_heavy_task[physician] = period['days'][-1]

        self.revenue_distribution[physician] += task.revenue


class MathSchedule:
    def __init__(self, physician_manager, task_manager, calendar):
        self.physician_manager = physician_manager
        self.task_manager = task_manager
        self.calendar = calendar
        self.scheduling_period = None
        self.task_splits = {}
        self.schedule = defaultdict(list)  # unique solution
        self.task_matcher = TaskMatcher(physician_manager, task_manager)
        self.off_days = {}
        self.assigned_calls = defaultdict(lambda: defaultdict(int))

        logging.debug("Schedule initialized with physician_manager, task_manager, and calendar")

    def set_scheduling_period(self, start_date: date, end_date: date):
        self.scheduling_period = (start_date, end_date)
        logging.debug(f"Scheduling period set to {self.scheduling_period}")

    def set_task_splits(self, task_splits: Dict[str, Dict[str, str]]):
        self.task_splits = task_splits
        logging.debug(f"Task splits set to {self.task_splits}")

    def set_off_days(self, off_days: Dict[str, List[date]]):
        self.off_days = off_days
        logging.debug(f"Off days set to {self.off_days}")

    def _load_schedule_from_file(self, filename):
        """
        Load and test the schedule from a JSON file.

        Args:
            filename:

        Raises:
            AssertionError whenever there is a mistake in the schedule format.
        """
        with open(filename, 'r') as f:
            loaded_schedule = json.load(f)

        schedule = defaultdict(list, {
            k: [
                {
                    **t,
                    'start_date': date.fromisoformat(t['start_date']),
                    'end_date': date.fromisoformat(t['end_date']),
                    'task': self.task_manager.get_task(t['task'])
                }
                for t in v
            ]
            for k, v in loaded_schedule.items()
        })

        # test loaded schedule
        all_phycians = self._get_all_physicians()
        for physician, task_list in schedule.items():
            assert physician in all_phycians, f"Physician {physician} is not recognized!"
            for task_index, task_dict in enumerate(task_list):
                task = task_dict['task']
                start_date = task_dict['start_date']
                end_date = task_dict['end_date']
                task_number_and_physician_str = f"task number {task_index + 1} and physician {physician}"
                assert isinstance(task, Task), f"Task ({task}) number {task_index + 1} is not recognized for physician {physician}!"
                assert isinstance(start_date, datetime.date), f"Start date {start_date} is not a date for {task_number_and_physician_str}!"
                assert isinstance(end_date,
                                  datetime.date), f"End date {end_date} is not a date for {task_number_and_physician_str}!"
                assert start_date <= end_date, f"Start ({start_date}) and end ({end_date}) date are not coherent for {task_number_and_physician_str}!"
                days = task_dict['days']
                assert date.fromisoformat(days[0]) == start_date, f"First date ({days[0]}) in 'days' is not the start date ({start_date}) for {task_number_and_physician_str}!"
                assert date.fromisoformat(days[-1]) == end_date, f"Last date ({days[-1]}) in 'days' is not the end date ({end_date}) for {task_number_and_physician_str}!"
                for i in range(len(days) - 1):
                    assert date.fromisoformat(days[i+1]) == date.fromisoformat(days[i]) + datetime.timedelta(days=1), f"Dates in 'days' are not continuous for {task_number_and_physician_str}!"

        return schedule

    def _math_load_initial_schedule(self):
        """
        Use loaded schedule as an initial solution.

        Notes:
            This schedule/solution can be partial or complete.

        Warnings:
            The schedule must be loaded in self.schedule before. You can use `load_schedule()` for instance.
        """
        assert self.schedule
        task_index = -1
        physician = None
        vars = []    # variables for the loaded schedule
        values = []  # values from the loaded schedule
        try:
            for physician, task_list in self.schedule.items():
                for task_index, task_dict in enumerate(task_list):
                    task = task_dict['task']
                    vars.append(self.y[(task.name, task_dict['start_date'], task_dict['end_date'], physician)].Index())
                    values.append(1)

            self.math_model._CpModel__model.solution_hint.vars.extend(vars)
            self.math_model._CpModel__model.solution_hint.values.extend(values)

        except Exception as e:
            raise RuntimeError(f"The initial schedule does not correspond to the problem \n"
                  f" physician {physician} at task number {task_index + 1}: {e}")

    def generate_schedule(self, use_initial_schedule=False):
        """
        Generate a schedule given all the instance information.

        Args:
            use_initial_schedule (bool): If `True`, use the loaded schedule as a start point to solve this
                instance.
        """
        if not self.scheduling_period:
            raise ValueError("Scheduling period must be set before generating schedule")

        if use_initial_schedule:
            assert self.schedule, f"No initial schedule was provided to start the search!"

        logging.debug("Generating schedule")
        extended_end_date = self._extend_scheduling_period()
        logging.debug(f"Scheduling period extended to {extended_end_date}")

        periods = self.calendar.determine_periods()
        relevant_periods = self._filter_relevant_periods(periods, extended_end_date)
        logging.debug(f"Filtered relevant periods: {relevant_periods}")

        # create mathematical model
        self.math_model = cp_model.CpModel()

        # create variables, constraints and objective function
        self._math_create_variables(periods=relevant_periods)
        self._math_create_constraints(periods=relevant_periods)
        self._math_create_objective_function()  # TODO: adapt scores to the objective function

        if use_initial_schedule:
            self._math_load_initial_schedule()

        # Creates the solver and solve
        self.math_solver = cp_model.CpSolver()
        status = self.math_solver.solve(self.math_model)

        # test the solution/schedule
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            logging.info(f"Schedule solved with status: {cp_model.CpSolver.status_name(self.math_solver)}")
            self._math_set_solution(periods=relevant_periods)
        else:
            logging.info(f"Schedule infeasible")

        logging.debug("Schedule generated")

    def _get_periods_days(self, week_periods):
        """
        Get all MAIN and CALL days.

        Args:
            week_periods:

        Returns:
            (A, B) with A (MAIN) and B (MAIN) list of list of continuous days.
        """
        main_periods_days = []
        call_periods_days = []
        for period in week_periods:
            if period['type'] == 'MAIN':
                main_periods_days.append(period['days'])
            elif period['type'] == 'CALL':
                call_periods_days.append(period['days'])
            else:
                raise NotImplementedError(f"Period type {period['type']} not recognized!")

        return main_periods_days, call_periods_days

    def _get_all_math_tasks_per_task(self, periods):
        """
        Create a dict with all `MathTask` for the given periods.

        Args:
            periods:

        Returns:
            A dict with entries [task.name] = [MathTask1, MathTask2, MathTask3, ...]. All task are non overlapping and
            ordered sequentially following the date.
        """
        # create output dict
        math_tasks_dict = {}
        for task in self.task_manager.data['tasks']:
            math_tasks_dict[task.name] = []

        # populate if in sequential order (granted because self.math_tasks is already ordered)
        for week_start, week_periods in periods.items():
            for task in self.task_manager.data['tasks']:
                math_tasks_dict[task.name].extend(self.math_tasks[task.name][week_start])

        return math_tasks_dict

    def _math_create_variables(self, periods):
        """
        Create the mathematical variables.

        A variable corresponds to the assignement or not of one physician to a `MathTask`. Each variable is
        indexed by `(task_name, start_date, end_date, physician)`.

        Args:
            periods:

        """
        self.y = {}  # x[("CTU_A", start_date, end_date, physician)]  MAIN and CALL tasks
        self.math_tasks = {}  # math_tasks["CTU_A"][week_start] = [MathTask1, MathTask2, ...]
        for task in self.task_manager.data['tasks']:
            self.math_tasks[task.name] = {}

        # variables exist for **all** mathematical tasks (MathTask), whether a physician is available or not
        all_physicians = self._get_all_physicians()

        for week_start, week_periods in periods.items():
            # [[day1, day2, day3], [day5]], [[day4], [day6, day7]]
            main_periods_days, call_periods_days = self._get_periods_days(week_periods=week_periods)

            for task in self.task_manager.data['tasks']:
                task_category = task.category  # for later
                self.math_tasks[task.name][week_start] = []

                if task.type == TaskType.MAIN:
                    if task_category.days_parameter == TaskDaysParameter.DISCONTINUOUS:
                        # TODO: implement DISCONTINUOUS?
                        raise NotImplementedError(
                            f"Task Category days parameters {TaskDaysParameter.DISCONTINUOUS} not yet implemented")
                    elif task_category.days_parameter in [TaskDaysParameter.CONTINUOUS, TaskDaysParameter.MULTI_WEEK]:

                        for index, main_period_days in enumerate(main_periods_days):
                            # Could be empty
                            available_physicians = self._get_available_physicians(main_period_days)

                            start_date = main_period_days[0]
                            end_date = main_period_days[-1]

                            self.math_tasks[task.name][week_start].append(
                                MathTask(
                                    name=task.name,
                                    task_type=task.type,
                                    y_vars=self.y,
                                    index=index,
                                    week_start=week_start,
                                    days=main_period_days,
                                    start_date=start_date,
                                    end_date=end_date,
                                    number_of_weeks=task.number_of_weeks,
                                    available_physicians=available_physicians,
                                    heaviness=task.heaviness,
                                    mandatory=task.mandatory
                                )
                            )
                            # vars
                            for physician in all_physicians:
                                self.y[(task.name, start_date, end_date, physician)] = self.math_model.new_bool_var(
                                    f"{task.name}_{start_date}_{end_date}_{physician}")
                    else:
                        raise NotImplementedError(
                            f"Task Category days parameters of type {type(task_category.days_parameter)} is unknown"
                        )

                elif task.type == TaskType.CALL:
                    if task_category.days_parameter == TaskDaysParameter.DISCONTINUOUS:
                        # TODO: implement DISCONTINUOUS?
                        raise NotImplementedError(
                            f"Task Category days parameters {TaskDaysParameter.DISCONTINUOUS} not yet implemented")
                    elif task_category.days_parameter in [TaskDaysParameter.CONTINUOUS, TaskDaysParameter.MULTI_WEEK]:
                        for index, call_period_days in enumerate(call_periods_days):
                            # Could be empty
                            available_physicians = self._get_available_physicians(call_period_days)

                            start_date = call_period_days[0]
                            end_date = call_period_days[-1]

                            self.math_tasks[task.name][week_start].append(
                                MathTask(
                                    name=task.name,
                                    task_type=task.type,
                                    y_vars=self.y,
                                    index=index,
                                    week_start=week_start,
                                    days=call_period_days,
                                    start_date=start_date,
                                    end_date=end_date,
                                    number_of_weeks=task.number_of_weeks,
                                    available_physicians=available_physicians,
                                    heaviness=task.heaviness,
                                    mandatory=task.mandatory
                                )
                            )
                            # vars
                            for physician in all_physicians:
                                self.y[(task.name, start_date, end_date, physician)] = self.math_model.new_bool_var(
                                    f"{task.name}_{start_date}_{end_date}_{physician}")
                else:
                    raise TypeError(f"Task type {task.type} not implemented")

    def _math_create_constraints(self, periods):
        """
        Create all constraints for the scheduling problem.

        Notes:
            You can comment one family of constraints to see what happens.

        Args:
            periods:

        """
        self._math_create_physician_availability_constraints(periods=periods)
        self._math_create_mandatory_task_constraints(periods=periods)
        self._math_create_call_linked_to_main_tasks_constraints(periods=periods)
        self._math_create_non_simultaneous_tasks(periods=periods)

    def _math_create_physician_availability_constraints(self, periods):
        """
        Forbid non-available physicians for the `MathTask`.

        Args:
            periods:
        """
        all_physicians = self._get_all_physicians()
        for week_start, week_periods in periods.items():
            for task in self.task_manager.data['tasks']:
                for index, math_task in enumerate(self.math_tasks[task.name][week_start]):
                    available_physicians = math_task.available_physicians
                    for physician in all_physicians:
                        if physician not in available_physicians:
                            self.math_model.add(self.y[(task.name, math_task.start_date, math_task.end_date, physician)] == 0)

    def _math_create_mandatory_task_constraints(self, periods):
        """
        Create the mandatory tasks constraints.

        Args:
            periods:
        """
        for week_start, week_periods in periods.items():
            for task in self.task_manager.data['tasks']:
                task_category = task.category  # for later
                if task.mandatory:
                    for index, math_task in enumerate(self.math_tasks[task.name][week_start]):
                        available_physicians = math_task.available_physicians
                        self.math_model.add(sum([self.y[(task.name, math_task.start_date, math_task.end_date, physician)] for physician in available_physicians]) >= 1)

    def _math_create_call_linked_to_main_tasks_constraints(self, periods):
        """
        Construct
        Args:
            periods:

        Warnings:
            The constraints are constructed for all physicians, whether they are available or not.

            Two conceptual types of constraints (more are really constructed) are constructed at once:
            1. the constraints linking the MAIN `MathTask`s with the CALL `MathTask` and
            2. the constraints linking the right number of `MathTask`s for one Task, i.e. linking the
                `MathTask`s for `number_of_weeks`.

        """
        def create_math_tasks_bundle_constraints(M, physicians):
            """
            One physician must complete all the `MathTask` or none during the right number of weeks.

            Args:
                M (List[MathTask]):
                physicians:
            """
            number_of_math_tasks = len(M)

            for physician in physicians:
                for i in range(number_of_math_tasks - 1):
                    self.math_model.add(M[i].y_var(physician) == M[i+1].y_var(physician))

        def limit_number_of_call_math_tasks(C, physicians, max_nbr_linked_call_math_tasks=1):
            """
            Limit the number of allowed CALL tasks.

            Args:
                C:
                physicians:
                max_nbr_linked_call_math_tasks:
            """
            for physician in physicians:
                self.math_model.add(sum(C[i].y_var(physician) for i in range(len(C))) <= max_nbr_linked_call_math_tasks)

        def link_main_and_call_math_tasks(M, C, physicians):
            """
            Link the MAIN and CALL tasks.

            Args:
                M:
                C:
                physicians:

            """
            # forbid early call math tasks
            first_possible_call_date = M[0].end_date

            for j in range(len(C)):
                if C[j].start_date <= first_possible_call_date:
                    for physician in physicians:
                        self.math_model.add(C[j].y_var(physician) == 0)
                else:
                    # call math tasks are ordered
                    break

            # if a physician is doing a MAIN task, she must do a CALL task too
            for physician in physicians:
                for i in range(len(M)):
                    if len(C) > 0:
                        self.math_model.add(M[i].y_var(physician) <= sum(C[j].y_var(physician) for j in range(len(C))))

            # if a physician is doing a CALL task, she must do the corresponding MAIN tasks too
            for physician in physicians:
                for j in range(len(C)):
                    if len(M) > 0:
                        self.math_model.add(C[j].y_var(physician) <= sum(M[i].y_var(physician) for i in range(len(M))))

        all_physicians = self._get_all_physicians()
        all_math_tasks_dict = self._get_all_math_tasks_per_task(periods=periods)
        all_tasks_list = self.task_manager.data['tasks']

        for task in all_tasks_list:
            if task.type == TaskType.MAIN:
                number_of_weeks_left = task.number_of_weeks  # counter to bundle MathTask for the right number of weeks
                # is there a linked call task?
                linked_call_task_name = self.task_manager.data['linkage_manager'].get_linked_call(task)
                bundled_main_tasks = []
                bundled_call_tasks = []
                for week_start, week_periods in periods.items():
                    bundled_main_tasks.extend(self.math_tasks[task.name][week_start])
                    if linked_call_task_name:
                        bundled_call_tasks.extend(self.math_tasks[linked_call_task_name][week_start])
                    number_of_weeks_left -= 1
                    if not number_of_weeks_left:
                        create_math_tasks_bundle_constraints(bundled_main_tasks, all_physicians)
                        if linked_call_task_name:
                            limit_number_of_call_math_tasks(bundled_call_tasks, all_physicians)
                            link_main_and_call_math_tasks(bundled_main_tasks, bundled_call_tasks, all_physicians)
                        # reset for the next bundle of MAIN MathTasks
                        bundled_main_tasks = []
                        bundled_call_tasks = []
                        number_of_weeks_left = task.number_of_weeks

    def _math_create_non_simultaneous_tasks(self, periods):
        """
        Forbid one physician to do two simultaneous `MathTask`.

        Args:
            periods:

        Notes:
            To allow for simultaneous tasks, simply remove those tasks for the list of `MathTask`s.
            For more complex tasks, for instance if for one physician, some tasks could be simultaneous, rewrite
            this method and `_create_mutually_exclusive_math_tasks_constraints` accordingly.
        """
        # get all MathTasks for all periods
        all_math_tasks_dict = self._get_all_math_tasks_per_task(periods=periods)
        all_tasks_list = self.task_manager.data['tasks']
        nbr_of_tasks = len(all_tasks_list)

        for i in range(nbr_of_tasks):
            for j in range(i+1, nbr_of_tasks):
                self._create_mutually_exclusive_math_tasks_constraints(
                    all_math_tasks_dict[all_tasks_list[i].name],
                    all_math_tasks_dict[all_tasks_list[j].name]
                )

    def _create_mutually_exclusive_math_tasks_constraints(self, A, B):
        """
        Add mutually exclusive constraints between two ordered lists of `MathTask`s.

        Warnings:
            This is done for all physicians, whether they participate in a `MathTask` or not.
            This is done in O(len(A) + len(B)).

        Args:
            A (List[MathTask]):
            B (List[MathTask]):
        """
        all_physicians = self._get_all_physicians()
        i = j = 0
        while i < len(A) and j < len(B):
            # Let's check if A[i] intersects B[j].
            # lo - the startpoint of the intersection
            # hi - the endpoint of the intersection
            lo = max(A[i].start_date, B[j].start_date)
            hi = min(A[i].end_date, B[j].end_date)
            if lo <= hi:
                # both interval intersect => add a mutually exclusive constraint for all physicians
                for physician in all_physicians:
                    self.math_model.add(A[i].y_var(physician) + B[j].y_var(physician) <= 1)

            # Remove the interval with the smallest endpoint
            if A[i].end_date < B[j].end_date:
                i += 1
            else:
                j += 1

    def _math_create_objective_function(self):
        """
        Create the objective function.

        This is how the preferences of the physicians are implemented.

        """
        #TODO: the folling code is dummy => implement this!
        vv = None
        for k, v in self.math_tasks.items():
            for kk, vv in v.items():
                break
            break
        self.math_model.maximize(vv[0].y_var(vv[0].available_physicians[0]) * 4)

    def _math_set_solution(self, periods):
        """
        Translate the mathematical solution into a schedule.

        Args:
            periods:
        """
        solver = self.math_solver

        # init solution schedule
        self.schedule = defaultdict(list)

        for week_start, week_periods in periods.items():
            for task in self.task_manager.data['tasks']:
                task_category = task.category  # for later
                for index, math_task in enumerate(self.math_tasks[task.name][week_start]):
                    available_physicians = math_task.available_physicians
                    for physician in available_physicians:
                        if solver.value(self.y[(task.name, math_task.start_date, math_task.end_date, physician)]) > 0:
                            self._add_to_schedule(
                                physician=physician,
                                task=task,
                                period={"days": math_task.days},
                                score=0  # TODO: add right score
                            )

    def _handle_extended_tasks(self, extended_end_date: date):
        for task in self.task_manager.data['tasks']:
            if task.number_of_weeks > 1:
                last_assigned = max(
                    (t['end_date'] for t in self.schedule.values() for t in t if t['task'].name == task),
                    default=None)
                if last_assigned and last_assigned < extended_end_date:
                    remaining_weeks = (extended_end_date - last_assigned).days // 7
                    for week in range(remaining_weeks):
                        start_date = last_assigned + timedelta(weeks=week + 1)
                        end_date = start_date + timedelta(days=6)
                        period = {'days': [start_date + timedelta(days=i) for i in range(7)], 'month': start_date.month}
                        available_physicians = self._get_available_physicians(period['days'])
                        self._assign_main_task(start_date, period, available_physicians, task)

    def _extend_scheduling_period(self) -> date:
        max_task_duration = max(task.number_of_weeks for task in self.task_manager.data['tasks'])
        extended_end_date = self.scheduling_period[1] + timedelta(weeks=max_task_duration)
        return extended_end_date

    def _filter_relevant_periods(self, periods: Dict[str, List[Dict[str, Any]]], end_date: date) -> Dict[
        str, List[Dict[str, Any]]]:
        return {
            week_start: week_periods
            for week_start, week_periods in periods.items()
            if date.fromisoformat(week_start) <= end_date
        }

    def _assign_tasks_for_period(self, week_start: date, periods: List[Dict[str, Any]]):
        for task in self.task_manager.data['tasks']:
            if task.type == TaskType.MAIN:
                if main_period := self._get_main_candidate(periods):
                    available_physicians = self._get_available_physicians(main_period['days'])
                    assigned_physician = self._assign_main_task(week_start, main_period, available_physicians, task)

                    if assigned_physician:
                        # Assign linked call task immediately after main task
                        linked_call_task_name = self.task_manager.data['linkage_manager'].get_linked_call(task)
                        linked_call_task = next(
                            (t for t in self.task_manager.data['tasks'] if t.name == linked_call_task_name), None)

                        if linked_call_task:
                            call_period = self._get_call_candidate(periods)
                            if call_period:
                                self._assign_linked_call_task(week_start, call_period, assigned_physician,
                                                              linked_call_task)

        # Handle remaining unassigned call tasks
        for task in self.task_manager.data['tasks']:
            if task.type == TaskType.CALL and task.name not in self.task_manager.data['linkage_manager'].links.values():
                if call_period := self._get_call_candidate(periods):
                    available_physicians = self._get_available_physicians(call_period['days'])
                    self._assign_call_task(week_start, call_period, available_physicians, task)

    def _assign_main_task(self, week_start: date, period: Dict[str, Any], available_physicians: List[str], task):
        period['month'] = week_start.month
        physician, score = self.task_matcher.find_best_match(available_physicians, task, period, week_start.month)
        if physician:
            for week in range(task.number_of_weeks):
                current_period = self._get_period_for_date(week_start + timedelta(weeks=week), 'MAIN')
                if current_period is None:
                    logging.debug(f"Only CALL periods found for {week_start + timedelta(weeks=week)}")
                else:
                    if not self._is_task_already_assigned(task, current_period) and not self._is_physician_already_assigned(physician, current_period):
                        self._add_to_schedule(physician, task, current_period, score)
                        self.task_matcher.update_physician_stats(physician, task, current_period)
                    else:
                        logging.debug(f"Task {task.name} is already assigned during {current_period['days']} or physician {physician} is already assigned another task")
            if physician in available_physicians:
                available_physicians.remove(physician)
            logging.debug(f"Assigned main task {task.name} to {physician} for {task.number_of_weeks} weeks")
            return physician
        else:
            logging.debug(f"No eligible physician found for main task {task.name}")
            return None

    def _assign_linked_call_task(self, week_start: date, period: Dict[str, Any], physician: str, task):
        if not self._is_task_already_assigned(task, period) and not self._is_physician_already_assigned(physician, period):
            if 'month' not in period:
                period['month'] = period['days'][0].month
            if self.assigned_calls[physician][period['month']] == 0:
                self._add_to_schedule(physician, task, period, 0)
                self.task_matcher.update_physician_stats(physician, task, period)
                self.assigned_calls[physician][period['month']] += 1
                logging.debug(f"Assigned linked call task {task.name} to {physician}")
            else:
                logging.debug(f"Unable to assign linked call task {task.name} to {physician} due to monthly call limit")
        else:
            logging.debug(f"Unable to assign linked call task {task.name} to {physician} due to conflicts")

    def _assign_call_task(self, week_start: date, period: Dict[str, Any], available_physicians: List[str], task):
        period['month'] = week_start.month
        physician, score = self.task_matcher.find_best_match(available_physicians, task, period, week_start.month)
        if physician:
            if not self._is_task_already_assigned(task, period) and not self._is_physician_already_assigned(physician, period):
                if self.assigned_calls[physician][period['month']] == 0:
                    self._add_to_schedule(physician, task, period, score)
                    available_physicians.remove(physician)
                    self.task_matcher.update_physician_stats(physician, task, period)
                    self.assigned_calls[physician][period['month']] += 1
                    logging.debug(f"Assigned call task {task.name} to {physician}")
                else:
                    logging.debug(f"Unable to assign call task {task.name} to {physician} due to monthly call limit")
            else:
                logging.debug(f"Task {task.name} is already assigned during {period['days']} or physician {physician} is already assigned another task")
        else:
            logging.debug(f"No eligible physician found for call task {task.name}")

    def _is_physician_already_assigned(self, physician: str, period: Dict[str, Any]) -> bool:
        for assigned_task in self.schedule[physician]:
            if any(day in period['days'] for day in assigned_task['days']):
                return True
        return False

    def _is_task_already_assigned(self, task: Any, period: Dict[str, Any]) -> bool:
        for physician, tasks in self.schedule.items():
            for assigned_task in tasks:
                if assigned_task['task'].name == task.name and any(day in period['days'] for day in assigned_task['days']):
                    return True
        return False
    def _get_period_for_date(self, date: date, type = str) -> Dict[str, Any]:
        """
        Returns the period dictionary for a given date.
        """
        logging.debug(f"Getting period for date {date}")
        try:
            periods = self.calendar.determine_periods()
            date_string = date.strftime('%Y-%m-%d')
            candidates = periods[date_string]
            return self._get_call_candidate(candidates) if type == 'CALL' else self._get_main_candidate(candidates)
        except:
            raise ValueError(f"No period found for date: {date}")

    def _get_call_candidate(self, candidates):
        return next((candidate for candidate in candidates if candidate['type'] == 'CALL'), None)

    def _get_main_candidate(self, candidates):
        return next((candidate for candidate in candidates if candidate['type'] == 'MAIN'), None)

    def _get_available_physicians(self, days: List[date]) -> List[str]:
        return [
            physician.name
            for physician in self.physician_manager.data['physicians']
            if all(not self.physician_manager.is_unavailable(physician.name, day) for day in days)
        ]

    def _get_all_physicians(self):
        return [
            physician.name
            for physician in self.physician_manager.data['physicians']
        ]

    def _add_to_schedule(self, physician: str, task: Any, period: Dict[str, Any], score: float):
        self.schedule[physician].append({
            'task': task,
            'days': period['days'],
            'start_date': period['days'][0],
            'end_date': period['days'][-1],
            'score': score
        })

    def get_schedule(self) -> Dict[str, List[Dict[str, Any]]]:
        return dict(self.schedule)

    def print_schedule(self):
        for physician, tasks in self.schedule.items():
            print(f"\n{physician}:")
            for task in tasks:
                print(f"  {task['task'].name}: {task['start_date']} - {task['end_date']} (Score: {task['score']:.2f})")

    def check_conflicts(self):
        conflicts = []
        for physician, tasks in self.schedule.items():
            sorted_tasks = sorted(tasks, key=lambda x: x['start_date'])
            for i in range(len(sorted_tasks) - 1):
                if sorted_tasks[i]['end_date'] >= sorted_tasks[i + 1]['start_date']:
                    conflicts.append(
                        f"Conflict for {physician}: {sorted_tasks[i]['task'].name} and {sorted_tasks[i + 1]['task'].name} overlap")
        return conflicts

    def save_schedule(self, filename):

        serializable_schedule = {
            physician: [
                {**task, 'task': task['task'].name}
                for task in tasks
            ]
            for physician, tasks in self.schedule.items()
        }
        with open(filename, 'w') as f:
            json.dump(serializable_schedule, f, indent=2, default=str)

    def load_schedule(self, filename):
        """
        Load schedule from a JSON file.

        Raises:
            AssertionError is the JSON format is not respected.

        Args:
            filename:
        """
        self.schedule = self._load_schedule_from_file(filename=filename)

    def get_statistics(self):
        stats = {}
        for physician, tasks in self.schedule.items():
            physician_stats = defaultdict(int)
            total_days = 0
            for task in tasks:
                physician_stats[task['task'].name] += 1
                total_days += (task['end_date'] - task['start_date']).days + 1

            working_weeks = total_days / 7
            physician_obj = self.physician_manager.get_physician_by_name(physician)
            desired_weeks_met = working_weeks >= physician_obj.desired_working_weeks * 52

            stats[physician] = {
                'task_counts': dict(physician_stats),
                'total_working_days': total_days,
                'working_weeks': working_weeks,
                'desired_weeks_met': desired_weeks_met
            }
        return stats

    def get_unassigned_tasks(self):
        all_tasks = set(task.name for task in self.task_manager.data['tasks'])
        assigned_tasks = set(task['task'].name for tasks in self.schedule.values() for task in tasks)
        return all_tasks - assigned_tasks

    def generate_ics_calendar(self, filename):
        cal = IcsCalendar()
        for physician, tasks in self.schedule.items():
            for task in tasks:
                event = Event()
                event.name = f"{task['task'].name} - {physician}"
                event.begin = task['start_date'].isoformat()
                event.end = (task['end_date'] + timedelta(days=1)).isoformat()  # End date should be exclusive
                event.description = f"Task: {task['task'].name}\nPhysician: {physician}\nScore: {task['score']}"
                cal.events.add(event)

        with open(filename, 'w') as f:
            f.writelines(cal)
