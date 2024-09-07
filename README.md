### README

# Physician Task Scheduler

## Overview
The Physician Task Scheduler is a Python-based application designed to manage and schedule tasks for physicians. It ensures that tasks are assigned based on physician availability, preferences, and task requirements.

## Features
- **Task Management**: Define and manage different categories of tasks.
- **Physician Management**: Add and manage physician profiles, including their preferences and availability.
- **Scheduling**: Automatically generate schedules based on defined tasks and physician availability.
- **Conflict Checking**: Identify and resolve scheduling conflicts.
- **Statistics**: Generate statistics on physician workloads and task assignments.
- **Export**: Save schedules to JSON and generate iCalendar files.

## Installation
1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/physician-task-scheduler.git
    cd physician-task-scheduler
    ```
2. Install the required dependencies:
    ```sh
    pip install -r requirements.txt
    ```

## Usage
1. **Initialize Managers**:
    ```python
    from config.managers import TaskManager, PhysicianManager
    from models.calendar import Calendar
    from models.schedule import Schedule
    from datetime import date
    
    task_manager = TaskManager()
    physician_manager = PhysicianManager(task_manager)
    ```

2. **Add Task Categories and Tasks**:
    ```python
    from models.task import TaskCategory, Task, TaskDaysParameter
    
    ctu_category = TaskCategory(
        name="CTU",
        days_parameter=TaskDaysParameter.MULTI_WEEK,
        number_of_weeks=2,
        weekday_revenue=2000,
        call_revenue=4000,
        restricted=False
    )
    task_manager.add_category(ctu_category)
    task_manager.add_task(Task.create(ctu_category, 'Main', 'CTU_A', heaviness=4))
    ```

3. **Link Tasks:**  

    ```
    task_manager.link_tasks('CTU_A', 'CTU_AB_CALL')
    ```

    

4. **Add Physicians**:

    ```python
    from models.physician import Physician
    
    john_doe = Physician("John", "Doe", ["CTU", "ER"], True, 0.75, ["CTU"], ["CTU"])
    physician_manager.add_physician(john_doe)
    
    
    # Set Unavailability:  
    unavailability_periods = {
        "John Doe": [
            (date(2023, 1, 1), date(2023, 1, 7)),  # Jan 1-7
            date(2023, 1, 9),                      # Jan 9
        ]
    }
    physician_manager.set_unavailability_periods(unavailability_periods)
    ```

5. **Create Calendar**:

    ```python
    start_date = date(2023, 1, 1)
    end_date = date(2023, 1, 31)
    region = 'Canada/QC'
    calendar = Calendar.create_calendar(start_date, end_date, region)
    
    
    # Add Holidays:  
    calendar.add_holiday(date(2023, 1, 2)
    ```

6. **Generate Schedule**:
    ```python
    schedule = Schedule(physician_manager, task_manager, calendar)
    schedule.set_scheduling_period(start_date, end_date)
    schedule.generate_schedule()
    schedule.print_schedule()
    
    
    # Save/Load Schedule:  
    schedule.save_schedule("schedule.json")
    schedule.load_schedule("schedule.json")
    
    # Export to ICS:  
    schedule.generate_ics_calendar("schedule.ics"
    ```

7. **Save and Load Configurations**:
    ```python
    task_manager.save_config("task_config.json")
    physician_manager.save_config("physician_config.json")
    calendar.save_calendar("calendar.json")
    ```

8. **Visualize the schedule**:
    ```shell
    streamlit run streamlit_calendar_demo.py
    ```
    
## Contributing
1. Fork the repository.
2. Create a new branch (`git checkout -b feature-branch`).
3. Commit your changes (`git commit -am 'Add new feature'`).
4. Push to the branch (`git push origin feature-branch`).
5. Create a new Pull Request.

## License
This project is licensed under the MIT License.

---

### Documentation

#### `models/task.py`

- **TaskCategory**: Represents a category of tasks with shared properties and behaviors.
- **Task**: Represents an individual task instance, automatically created based on category settings.
- **LinkageManager**: Manages the linkage of tasks.

#### `models/physician.py`

- **Physician**: Represents a physician profile with attributes like name, preferred tasks, and availability.

#### `models/calendar.py`

- **Calendar**: Represents a scheduling calendar with methods to load holidays, determine periods, and save/load calendar state.

#### `config/managers.py`

- **ConfigurableManager**: Base class for managing configurations.
- **TaskManager**: Manages task categories and tasks.
- **PhysicianManager**: Manages physician profiles and their availability.

#### `main.py`

- Initializes and configures the `TaskManager` and `PhysicianManager`.
- Adds task categories, tasks, and physicians.
- Creates a calendar and generates a schedule.
- Saves and loads configurations.

#### `utils/dynamic.py`

- Placeholder for dynamic utility functions (to be fetched via API).



## Additional Features (Work In Progress)



## Urgent

- Fix the scheduling algorithm
  - Calls should always follow main tasks if those are linked
  - For CTU (tasks of two weeks), the linked call should occur between the two 'main' periods
  - Allocation score must be reviewed:
    - There are some elements that should always
  - Add additional elements in decision rule:
    - task.is_mandatory (parameter should be included)
  - Add discontinuity principle
    - Break main period and call tasks if multiple physicians with this preference.

### 1. Statistics

This feature provides detailed statistics for each physician based on the current schedule. It allows you to analyze the distribution of tasks and workload.

#### Usage:

To retrieve statistics:

```python
# Retrieve scheduling statistics for each physician
stats = schedule.get_statistics()

# Print statistics for each physician
for physician, stat in stats.items():
    print(f"{physician}: {stat}")
```

### 2. Unassigned Tasks

This feature lists tasks that have not been assigned to any physician. It helps identify scheduling gaps and ensures all tasks are allocated.

#### Usage:

To get unassigned tasks:

```python
# Retrieve unassigned tasks 
unassigned_tasks = schedule.get_unassigned_tasks() 

# Print each unassigned task 
for task in unassigned_tasks:    print(task)
```

