from typing import List, Dict, Any, Union
class Physician:
    """
    Represents a physician profile.

    Attributes:
        first_name (str): The first name of the physician.
        last_name (str): The last name of the physician.
        initials (str): The initials of the physician.
        preferred_tasks (list): The preferred task categories of the physician.
        discontinuity_preference (bool): Indicates if the physician prefers discontinuous tasks.
        desired_working_weeks (float): The desired working weeks percentage of the physician.
        restricted_tasks (list): The restricted task categories for the physician.
        exclusion_tasks (list): The excluded task categories for the physician.
    """
    ALLOWED_WORKING_WEEKS = {0, 0.25, 0.5, 0.75, 1}

    def __init__(self, first_name: str, last_name: str, preferred_tasks: List[str],
                 discontinuity_preference: bool, desired_working_weeks: float,
                 restricted_tasks: List[str], exclusion_tasks: List[str]):
        self.first_name = first_name
        self.last_name = last_name
        self.name = first_name + " " + last_name
        self.initials = ""  # Will be set by PhysicianManager
        self.preferred_tasks = preferred_tasks[:3]  # Limit to top 3
        self.discontinuity_preference = discontinuity_preference
        if desired_working_weeks not in self.ALLOWED_WORKING_WEEKS:
            raise ValueError(f"Invalid desired working weeks: {desired_working_weeks}. Must be one of {self.ALLOWED_WORKING_WEEKS}")
        self.desired_working_weeks = desired_working_weeks
        self.restricted_tasks = restricted_tasks
        self.exclusion_tasks = exclusion_tasks

    def to_dict(self) -> Dict[str, Any]:
        return {
            'first_name': self.first_name,
            'last_name': self.last_name,
            'name': self.name,
            'initials': self.initials,
            'preferred_tasks': self.preferred_tasks,
            'discontinuity_preference': self.discontinuity_preference,
            'desired_working_weeks': self.desired_working_weeks,
            'restricted_tasks': self.restricted_tasks,
            'exclusion_tasks': self.exclusion_tasks,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        physician = cls(
            first_name=data['first_name'],
            last_name=data['last_name'],
            preferred_tasks=data['preferred_tasks'],
            discontinuity_preference=data['discontinuity_preference'],
            desired_working_weeks=data['desired_working_weeks'],
            restricted_tasks=data['restricted_tasks'],
            exclusion_tasks=data['exclusion_tasks']
        )
        physician.initials = data['initials']
        return physician