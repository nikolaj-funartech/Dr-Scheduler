from datetime import date, timedelta
from typing import Dict, List, Any, Tuple
from collections import defaultdict
import calendar
from ics import Calendar as IcsCalendar, Event
import json
import logging
from models.task import TaskType

logging.basicConfig(level=logging.DEBUG)

# models/schedule.py

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

class Schedule:
    def __init__(self, physician_manager, task_manager, calendar):
        self.physician_manager = physician_manager
        self.task_manager = task_manager
        self.calendar = calendar
        self.scheduling_period = None
        self.task_splits = {}
        self.schedule = defaultdict(list)
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

    def generate_schedule(self):
        if not self.scheduling_period:
            raise ValueError("Scheduling period must be set before generating schedule")
        logging.debug("Generating schedule")
        extended_end_date = self._extend_scheduling_period()
        logging.debug(f"Scheduling period extended to {extended_end_date}")

        periods = self.calendar.determine_periods()
        relevant_periods = self._filter_relevant_periods(periods, extended_end_date)
        logging.debug(f"Filtered relevant periods: {relevant_periods}")

        for week_start, week_periods in relevant_periods.items():
            logging.debug(f"Assigning task for {week_periods}")
            self._assign_tasks_for_period(date.fromisoformat(week_start), week_periods)

        self._handle_extended_tasks(extended_end_date)

        logging.debug("Schedule generated")

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
        with open(filename, 'r') as f:
            loaded_schedule = json.load(f)
        self.schedule = defaultdict(list, {
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