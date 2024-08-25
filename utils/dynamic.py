## This file contains utility functions that are used to load and save dynamic data, such as unavailability periods for physicians
# This will eventually be fetched via API

import json
from datetime import date, datetime
from typing import Dict, List, Union, Tuple


def parse_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()

def load_unavailability_periods(filename: str) -> Dict[str, List[Union[date, Tuple[date, date]]]]:
    with open(filename, 'r') as f:
        data = json.load(f)

    unavailability_periods = {}
    for name, periods in data.items():
        unavailability_periods[name] = []
        for period in periods:
            if isinstance(period, str):
                unavailability_periods[name].append(parse_date(period))
            elif isinstance(period, list) and len(period) == 2:
                start_date = parse_date(period[0])
                end_date = parse_date(period[1])
                unavailability_periods[name].append((start_date, end_date))
            else:
                raise ValueError(f"Invalid period format for {name}: {period}")

    return unavailability_periods


def save_unavailability_periods(filename: str, unavailability_periods: Dict[str, List[Union[date, Tuple[date, date]]]]):
    data = {}
    for name, periods in unavailability_periods.items():
        data[name] = []
        for period in periods:
            if isinstance(period, date):
                data[name].append(period.isoformat())
            elif isinstance(period, tuple) and len(period) == 2:
                data[name].append([period[0].isoformat(), period[1].isoformat()])
            else:
                raise ValueError(f"Invalid period format for {name}: {period}")

    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

'''
    unavailability_periods = load_unavailability_periods("unavailability_periods.json")
    physician_manager.set_unavailability_periods(unavailability_periods)
'''

'''
{
  "John Doe": [
    ["2023-01-01", "2023-01-07"],
    "2023-01-09",
    ["2023-01-15", "2023-01-25"]
  ],
  "Jane Smith": [
    ["2023-02-01", "2023-02-14"],
    "2023-03-03",
    ["2023-04-10", "2023-04-15"]
  ],
  "Alice Johnson": [
    "2023-05-01",
    ["2023-06-15", "2023-06-20"],
    "2023-07-04"
  ]
}
'''