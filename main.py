from models.task import TaskCategory, Task, TaskDaysParameter
from models.physician import Physician
from models.calendar import Calendar
# from models.schedule import Schedule
from models.math_schedule import MathSchedule
from collections import defaultdict

from config.managers import TaskManager, PhysicianManager
from datetime import date, timedelta

# Initialize TaskManager and PhysicianManager
task_manager = TaskManager()
physician_manager = PhysicianManager(task_manager)

# Add categories
ctu_category = TaskCategory(
    name="CTU",
    days_parameter=TaskDaysParameter.MULTI_WEEK,
    number_of_weeks=2,
    weekday_revenue=2000,
    call_revenue=4000,
    restricted=False
)
task_manager.add_category(ctu_category)

er_category = TaskCategory(
    name="ER",
    days_parameter=TaskDaysParameter.CONTINUOUS,
    number_of_weeks=1,
    weekday_revenue=2500,
    call_revenue=5000,
    restricted=True
)
task_manager.add_category(er_category)

# Add tasks
task_manager.add_task(Task.create(ctu_category, 'Main', 'CTU_A', heaviness=4))
task_manager.add_task(Task.create(ctu_category, 'Main', 'CTU_B', week_offset=1, heaviness=4))
# task_manager.add_task(Task.create(ctu_category, 'Call', 'CTU_AB_CALL', heaviness=5))
task_manager.add_task(Task.create(ctu_category, 'Call', 'CTU_A_CALL', heaviness=5, mandatory=False))
task_manager.add_task(Task.create(ctu_category, 'Call', 'CTU_B_CALL', heaviness=5, mandatory=False))
task_manager.add_task(Task.create(er_category, 'Main', 'ER_1', heaviness=5))
task_manager.add_task(Task.create(er_category, 'Call', 'ER_CALL', heaviness=5, mandatory=False))

# Link tasks
# task_manager.link_tasks('CTU_A', 'CTU_AB_CALL')
# task_manager.link_tasks('CTU_B', 'CTU_AB_CALL')
task_manager.link_tasks('CTU_A', 'CTU_A_CALL')
task_manager.link_tasks('CTU_B', 'CTU_B_CALL')
task_manager.link_tasks('ER_1', 'ER_CALL')

# Save and load task configuration
task_manager.save_config("task_config.json")
loaded_task_manager = TaskManager.load_config("task_config.json")

# Verify loaded task data
print("Loaded Categories:", list(loaded_task_manager.data['categories'].keys()))
print("Loaded Tasks:", [task.name for task in loaded_task_manager.data['tasks']])
print("Loaded Linkages:", loaded_task_manager.data['linkage_manager'].links)

# Initialize PhysicianManager with loaded TaskManager
physician_manager = PhysicianManager(loaded_task_manager)

# Add physicians
john_doe = Physician("John", "Doe", ["CTU", "ER"], True, 0.75, ["CTU"], ["CTU"])
jane_smith = Physician("Jane", "Smith", ["ER", "CTU"], False, 1.0, ["ER"], [])
eric_yamga = Physician("Eric", "Yamga", ["ER", "CTU"], False, 1.0, ["ER"], [])
justine_munger = Physician("Justine", "Munger", ["ER", "CTU"], False, 1.0, ["ER"], [])

physician_manager.add_physician(john_doe)
physician_manager.add_physician(jane_smith)
physician_manager.add_physician(eric_yamga)
physician_manager.add_physician(justine_munger)

# Save and load physician configuration
physician_manager.save_config("physician_config.json")
loaded_physician_manager = PhysicianManager.load_config("physician_config.json", "task_config.json")

# Verify loaded physician data
print("Loaded Task Categories:", list(loaded_physician_manager.task_manager.data['categories'].keys()))
for physician in loaded_physician_manager.data['physicians']:
    print(f"Loaded Physician: {physician.first_name} {physician.last_name}")
    print(f"  Initials: {physician.initials}")
    print(f"  Preferred Tasks: {physician.preferred_tasks}")
    print(f"  Desired Working Weeks: {physician.desired_working_weeks}")

# Set unavailability periods
unavailability_periods = {
    "John Doe": [
        (date(2023, 1, 1), date(2023, 1, 7)),  # Jan 1-7
        date(2023, 1, 9),                      # Jan 9
    ],
    "Jane Smith": [
        (date(2023, 2, 1), date(2023, 2, 14)),  # Feb 1-14
        date(2023, 3, 3),                       # Mar 3
    ]
}
loaded_physician_manager.set_unavailability_periods(unavailability_periods)

# Add additional unavailability periods
loaded_physician_manager.add_unavailability("John", "Doe", (date(2023, 1, 15), date(2023, 1, 25)))
loaded_physician_manager.add_unavailability("Jane", "Smith", date(2023, 4, 10))

# Verify unavailability periods
print("John Doe's unavailability periods:", loaded_physician_manager.get_unavailability_periods("John Doe"))
print("John Doe's unavailability periods:", loaded_physician_manager.get_unavailability_periods("Jane Smith"))


# Create calendar


start_date = date(2023, 1, 2)
end_date = date(2023, 1, 30)
region = 'Canada/QC'
calendar = Calendar.create_calendar(start_date, end_date, region)
calendar.add_holiday(date(2023, 1, 2))


calendar.save_calendar("calendar.json")
loaded_calendar = Calendar.load_calendar("calendar.json")

periods = calendar.determine_periods()
calendar.preview_periods(periods)



# Scheduler
# Create the Schedule object
schedule = MathSchedule(loaded_physician_manager, loaded_task_manager, loaded_calendar)

# Set the scheduling period
start_date = date(2023, 1, 1)
end_date = date(2023, 1, 31)
schedule.set_scheduling_period(start_date, end_date)

# Set task splits (if needed)
task_splits = {
    "CTU": {"linked": "5:2", "unlinked": "5:2"},
    "ER": {"linked": "5:2", "unlinked": "5:2"}
}
schedule.set_task_splits(task_splits)



# Set the off days (example data)
off_days = {
    "CTU": [date(2023, 1, 3), date(2023, 12, 25)],
    "ER": [date(2023, 7, 4)]
}

# schedule.set_off_days(off_days)

# Generate the schedule
schedule.generate_schedule()

# Print the generated schedule

# You can also access the schedule as a dictionary
#schedule_dict = schedule.get_schedule()

# Example usage of the alias



# Generate and save calendar

schedule.generate_ics_calendar("generated_calendar.ics")


schedule.print_schedule()
