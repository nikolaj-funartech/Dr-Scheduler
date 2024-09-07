# -*- coding: utf-8 -*-
import datetime
import streamlit as st
from streamlit_calendar import calendar

HOLIDAY_DAY_COLOR = "#e6ffe6"  # light green
WEEKEND_DAY_COLOR = "#e6f2ff"  # light blue

calendar_options = {
    "editable": "true",
    "selectable": "true",
    "headerToolbar": {
        "left": "today prev,next",
        "center": "title",
        "right": "resourceTimelineDay,resourceTimelineWeek,resourceTimelineMonth",
    },
    "slotMinTime": "08:00:00",
    "slotMaxTime": "18:00:00",
    "initialView": "resourceTimelineMonth",
    "resourceGroupField": "physicians",

}

custom_css = """
    .fc-event-past {
        opacity: 0.8;
    }
    .fc-event-time {
        font-style: italic;
    }
    .fc-event-title {
        font-weight: 700;
    }
    .fc-toolbar-title {
        font-size: 2rem;
    }
    #calendar {
        width: 810px;
    }
"""

if __name__ == "__main__":
    import json

    ###########################################################################
    # LOAD DATA
    ###########################################################################
    with open("calendar.json", "r") as fp:
        schedule_calendar = json.load(fp=fp)

    with open("generated_schedule.json", "r") as fp:
        schedule = json.load(fp=fp)

    # WARNING: we need to add one day to the end date as the end dates are exclusive
    # see: https://fullcalendar.io/docs/v3/event-object
    for physician_id, physician_scheduled_tasks in schedule.items():
        for task in physician_scheduled_tasks:
            end_date_str = task["end_date"]
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d')
            end_date += datetime.timedelta(days=1)
            task["end_date"] = end_date.isoformat()

    ###########################################################################
    # CALENDAR OPTIONS
    ###########################################################################
    # create resources for all physicians (that are involved in the schedule)
    resources = []
    resources_dict = {}  # to find the exact resources involved
    # for physician_id, physician_scheduled_task in schedule.items():
    for physician_id in schedule.keys():
        resources_dict[physician_id] = {}
    for physician_id, physician_scheduled_tasks in schedule.items():
        for task in physician_scheduled_tasks:
            resources_dict[physician_id][task["task"]] = None
    # create specific resources with ids f"{physician_id}{task_name}"
    for physician_id, task_name_dict in resources_dict.items():
        for task_name in task_name_dict.keys():
            resources.append(
                {
                    "id": f"{physician_id}{task_name}",
                    "physicians": physician_id,
                    "title": task_name
                }
            )
    calendar_options["resources"] = resources
    calendar_options["initialDate"] = schedule_calendar["start_date"]

    ###########################################################################
    # CALENDAR EVENTS
    ###########################################################################
    calendar_events = []
    # create holidays
    for holiday in schedule_calendar["holidays"]:
        calendar_events.append(
            {
                "start": holiday,
                "end": holiday,
                "display": "background",
                "allDay": True,
                "backgroundColor": HOLIDAY_DAY_COLOR
            }
        )
    # create weekend days
    for weekend_day in schedule_calendar["weekend_days"]:
        calendar_events.append(
            {
                "start": weekend_day,
                "end": weekend_day,
                "display": "background",
                "allDay": True,
                "backgroundColor": WEEKEND_DAY_COLOR
            }
        )

    # create schedule events
    for physician_id, physician_scheduled_task in schedule.items():
        for task in physician_scheduled_task:
            calendar_events.append(
                {
                    "title": f"{task['task']} ({task['score']})",
                    "start": task['start_date'],
                    "end": task['end_date'],
                    "resourceId": f"{physician_id}{task['task']}",
                }
            )

    ###########################################################################
    # DISPLAY
    ###########################################################################
    calendar = calendar(events=calendar_events, options=calendar_options, custom_css=custom_css)
    st.write(calendar)
