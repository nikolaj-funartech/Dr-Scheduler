from enum import Enum
from typing import Optional, Dict, Set
from datetime import date

class TaskType(Enum):
    """Defines the type of tasks available."""
    MAIN = "Main"
    CALL = "Call"

class TaskDaysParameter(Enum):
    """Defines the scheduling parameters for task days."""
    DISCONTINUOUS = "Discontinuous"
    CONTINUOUS = "Continuous"
    MULTI_WEEK = "Multi-week"

class TaskCategory:
    """
    Represents a category of tasks with shared properties and behaviors.

    Attributes:
        name (str): The name of the task category.
        days_parameter (TaskDaysParameter): The days parameter for tasks in this category.
        number_of_weeks (int): The number of consecutive weeks a physician must be assigned to this task.
        weekday_revenue (float): The revenue for weekday tasks in this category.
        call_revenue (float): The revenue for call tasks in this category.
        restricted (bool): Indicates if tasks in this category are restricted to certain physicians.
    """
    def __init__(self, name: str, days_parameter: TaskDaysParameter, number_of_weeks: int,
                 weekday_revenue: float, call_revenue: float, restricted: bool = False):
        self.name = name
        self.days_parameter = days_parameter
        self.number_of_weeks = number_of_weeks
        self.weekday_revenue = weekday_revenue
        self.call_revenue = call_revenue
        self.restricted = restricted
        self.off_days: Set[date] = set()  # This will be populated by the scheduler

    def to_dict(self):
        return {
            "name": self.name,
            "days_parameter": self.days_parameter.value,
            "number_of_weeks": self.number_of_weeks,
            "weekday_revenue": self.weekday_revenue,
            "call_revenue": self.call_revenue,
            "restricted": self.restricted,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data["name"],
            days_parameter=TaskDaysParameter(data["days_parameter"]),
            number_of_weeks=data["number_of_weeks"],
            weekday_revenue=data["weekday_revenue"],
            call_revenue=data["call_revenue"],
            restricted=data["restricted"]
        )

class Task:
    """
    Represents an individual task instance, automatically created based on category settings.

    Attributes:
        category (TaskCategory): The category to which the task belongs.
        type (TaskType): The type of the task (Main or Call).
        name (str): The name of the task.
        week_offset (int): The week offset for scheduling purposes.
        heaviness (int): The heaviness or difficulty of the task (scale 0-5).
        mandatory (bool): Indicates if the task is mandatory or optional.
    """

    def __init__(self, category: TaskCategory, task_type: str, name: str,
                 week_offset: int = 0, heaviness: int = 0, mandatory: bool = True):
        self.category = category
        self.type = TaskType(task_type)
        self.name = name
        self.week_offset = week_offset
        self.heaviness = heaviness
        self.mandatory = mandatory
        self.number_of_weeks = 1 if self.type == TaskType.CALL else self.category.number_of_weeks

    @classmethod
    def create(cls, category, task_type, name, week_offset=0, heaviness=0, mandatory=True):
        return cls(category, task_type, name, week_offset, heaviness, mandatory)

    def to_dict(self):
        return {
            "category": self.category.name,
            "type": self.type.value,
            "name": self.name,
            "week_offset": self.week_offset,
            "heaviness": self.heaviness,
            "mandatory": self.mandatory,
        }

    @classmethod
    def from_dict(cls, data, categories):
        return cls(
            category=categories[data["category"]],
            task_type=data["type"],
            name=data["name"],
            week_offset=data["week_offset"],
            heaviness=data["heaviness"],
            mandatory=data["mandatory"]
        )

    @property
    def task_type(self) -> TaskType:
        return self.type

    @property
    def days_parameter(self) -> TaskDaysParameter:
        return self.category.days_parameter

    @property
    def revenue(self) -> float:
        return self.category.weekday_revenue if self.task_type == TaskType.MAIN else self.category.call_revenue

    @property
    def off_days(self) -> Set[date]:
        return self.category.off_days

    @property
    def is_heavy(self) -> bool:
        return self.heaviness >= 3
    @property
    def is_restricted(self) -> bool:
        return self.category.restricted
    @property
    def is_call_task(self) -> bool:
        return self.type == TaskType.CALL
    @property
    def is_mandatory(self) -> bool:
        return self.mandatory
    @property
    def is_discontinuous(self) -> bool:
        return self.category.days_parameter == TaskDaysParameter.DISCONTINUOUS

class LinkageManager:
    """
    Manages the linkage of tasks.

    Attributes:
        links (Dict[str, str]): A dictionary of task linkages.
    """
    def __init__(self):
        self.links: Dict[str, str] = {}

    def link_tasks(self, main_task: Task, call_task: Task):
        """Links a main task to a call task."""
        if main_task.type == TaskType.MAIN and call_task.type == TaskType.CALL:
            self.links[main_task.name] = call_task.name
        else:
            raise ValueError("Invalid linkage: Main tasks must link to Call tasks.")

    def unlink_task(self, main_task: Task):
        """Removes the linkage for a given main task."""
        self.links.pop(main_task.name, None)

    def get_linked_call(self, main_task: Task) -> Optional[str]:
        """Returns the linked call task for a given main task."""
        return self.links.get(main_task.name)

    def remove_task(self, task: Task):
        """Removes a task and its linkages from the manager."""
        self.links.pop(task.name, None)
        self.links = {main: call for main, call in self.links.items() if call != task.name}

    def to_dict(self):
        return self.links

    @classmethod
    def from_dict(cls, data):
        manager = cls()
        manager.links = data
        return manager


# Example usage
ctu_category = TaskCategory(
    name="CTU",
    days_parameter=TaskDaysParameter.MULTI_WEEK,
    number_of_weeks=2,
    weekday_revenue=2000,
    call_revenue=4000,
    restricted=False
)

linkage_manager = LinkageManager()

CTU_A = Task.create(ctu_category, 'Main', 'CTU_A', heaviness=4)
CTU_B = Task.create(ctu_category, 'Main', 'CTU_B', week_offset=1, heaviness=4)
CTU_C = Task.create(ctu_category, 'Main', 'CTU_C', heaviness=4)
CTU_D = Task.create(ctu_category, 'Main', 'CTU_D', week_offset=1, heaviness=4)

CTU_AB_CALL = Task.create(ctu_category, 'Call', 'CTU_AB_CALL', heaviness=5)
CTU_CD_CALL = Task.create(ctu_category, 'Call', 'CTU_CD_CALL', heaviness=5)

# Link tasks
linkage_manager.link_tasks(CTU_A, CTU_AB_CALL)
linkage_manager.link_tasks(CTU_B, CTU_AB_CALL)
linkage_manager.link_tasks(CTU_C, CTU_CD_CALL)
linkage_manager.link_tasks(CTU_D, CTU_CD_CALL)


