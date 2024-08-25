### This module contains classes that manage the configuration of tasks and physicians. They are wrappers around those different classes to provide an API friendly approach to modifying parameters.

import json
import logging

from typing import List, Dict, Any, Union, Tuple
from datetime import date
from models.task import TaskCategory, Task, LinkageManager, TaskDaysParameter, TaskType
from models.physician import Physician

logging.basicConfig(level=logging.DEBUG)

class ConfigurableManager:
    def __init__(self):
        self.data: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {key: value.to_dict() if hasattr(value, 'to_dict') else value
                for key, value in self.data.items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        raise NotImplementedError("Subclasses must implement this method")

    def save_config(self, filename: str):
        with open(filename, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_config(cls, filename: str):
        with open(filename, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)



class TaskManager(ConfigurableManager):
    def __init__(self):
        super().__init__()
        self.data['categories'] = {}
        self.data['tasks'] = []
        self.data['linkage_manager'] = LinkageManager()


    def is_linked(self):
        return self.data['linkage_manager']

    def add_category(self, category: TaskCategory):
        self.data['categories'][category.name] = category

    def add_task(self, task: Task):
        self.data['tasks'].append(task)

    def link_tasks(self, main_task_name: str, call_task_name: str):
        main_task = next((t for t in self.data['tasks'] if t.name == main_task_name), None)
        call_task = next((t for t in self.data['tasks'] if t.name == call_task_name), None)
        if main_task and call_task:
            self.data['linkage_manager'].link_tasks(main_task, call_task)
        else:
            print(f"Error: Could not find tasks to link.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'categories': [category.to_dict() for category in self.data['categories'].values()],
            'tasks': [task.to_dict() for task in self.data['tasks']],
            'linkage_manager': self.data['linkage_manager'].to_dict()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        manager = cls()
        categories = {cat_data['name']: TaskCategory.from_dict(cat_data) for cat_data in data['categories']}
        manager.data['categories'] = categories
        manager.data['tasks'] = [Task.from_dict(task_data, categories) for task_data in data['tasks']]
        manager.data['linkage_manager'] = LinkageManager.from_dict(data['linkage_manager'])
        return manager

class PhysicianManager(ConfigurableManager):
    def __init__(self, task_manager: Union[TaskManager, str]):
        super().__init__()
        self.data['physicians'] = []
        self.unavailability_periods: Dict[str, List[Union[date, tuple[date, date]]]] = {}

        if isinstance(task_manager, str):
            self.task_manager = TaskManager.load_config(task_manager)
        else:
            self.task_manager = task_manager

    def add_physician(self, physician: Physician):
        self._validate_physician(physician)
        self._set_initials(physician)
        self.data['physicians'].append(physician)
        self.unavailability_periods[f"{physician.first_name} {physician.last_name}"] = []

    def _validate_physician(self, physician: Physician):
        task_categories = set(self.task_manager.data['categories'].keys())

        invalid_preferred_tasks = [task for task in physician.preferred_tasks if task not in task_categories]
        if invalid_preferred_tasks:
            logging.debug(f"Invalid preferred tasks: {invalid_preferred_tasks}")
            logging.debug(f"Expected tasks: {task_categories}")
            raise ValueError("Invalid preferred tasks")

        invalid_restricted_tasks = [task for task in physician.restricted_tasks if task not in task_categories]
        if invalid_restricted_tasks:
            logging.debug(f"Invalid restricted tasks: {invalid_restricted_tasks}")
            logging.debug(f"Expected tasks: {task_categories}")
            raise ValueError("Invalid restricted tasks")

        invalid_exclusion_tasks = [task for task in physician.exclusion_tasks if task not in task_categories]
        if invalid_exclusion_tasks:
            logging.debug(f"Invalid exclusion tasks: {invalid_exclusion_tasks}")
            logging.debug(f"Expected tasks: {task_categories}")
            raise ValueError("Invalid exclusion tasks")

        if not 0 < physician.desired_working_weeks <= 1:
            logging.debug(f"Invalid desired working weeks: {physician.desired_working_weeks}")
            logging.debug("Expected: 0 < desired_working_weeks <= 1")
            raise ValueError("Desired working weeks must be between 0 and 1")

    def _set_initials(self, physician: Physician):
        initials = f"{physician.first_name[0]}{physician.last_name[0]}"
        if any(p.initials == initials for p in self.data['physicians']):
            initials = f"{physician.first_name[0]}{physician.first_name[1]}{physician.last_name[0]}"
        physician.initials = initials

    def get_physician_by_name(self, name: str) -> Physician:
        return next((p for p in self.data['physicians'] if p.name == name),
                    None)

    def set_unavailability_periods(self, unavailability_periods: Dict[str, List[Union[date, Tuple[date, date]]]]):
        # Safeguard: Check if all physicians in unavailability_periods exist in the PhysicianManager
        for physician_name in unavailability_periods.keys():
            if not any(f"{p.first_name} {p.last_name}" == physician_name for p in self.data['physicians']):
                raise ValueError(f"Physician '{physician_name}' not found in PhysicianManager")

        self.unavailability_periods = unavailability_periods

    def add_unavailability(self, first_name: str, last_name: str, period: Union[date, Tuple[date, date]]):
        physician_name = f"{first_name} {last_name}"
        if not any(p.first_name == first_name and p.last_name == last_name for p in self.data['physicians']):
            raise ValueError(f"Physician '{physician_name}' not found in PhysicianManager")

        if physician_name not in self.unavailability_periods:
            self.unavailability_periods[physician_name] = []

        if isinstance(period, date):
            self.unavailability_periods[physician_name].append(period)
        elif isinstance(period, tuple) and len(period) == 2 and all(isinstance(d, date) for d in period):
            self.unavailability_periods[physician_name].append(period)
        else:
            raise ValueError(f"Invalid unavailability period: {period}")

    def is_unavailable(self, name, check_date: date) -> bool:
        if name not in self.unavailability_periods:
            return False

        for period in self.unavailability_periods[name]:
            if isinstance(period, date):
                if check_date == period:
                    return True
            else:
                start, end = period
                if start <= check_date <= end:
                    return True
        return False

    def get_unavailability_periods(self, name) -> List[Union[date, Tuple[date, date]]]:
        return self.unavailability_periods.get(name, [])

    def save_config(self, filename: str):
        data = {
            'physicians': [physician.to_dict() for physician in self.data['physicians']]
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_config(cls, physician_config_filename: str, task_config_filename: str):
        with open(physician_config_filename, 'r') as f:
            physician_data = json.load(f)

        manager = cls(task_config_filename)
        for physician_dict in physician_data['physicians']:
            physician = Physician.from_dict(physician_dict)
            manager.add_physician(physician)

        return manager
