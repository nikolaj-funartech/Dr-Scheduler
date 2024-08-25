# models/calendar.py
import json
from datetime import date, timedelta
from typing import List, Dict, Any
import holidays
from collections import defaultdict

class Calendar:
    """
    Represents a scheduling calendar.

    Attributes:
        start_date (date): The start date of the calendar.
        end_date (date): The end date of the calendar.
        holidays (list): The list of holidays in the calendar.
        working_days (list): The list of working days in the calendar.
        weekend_days (list): The list of weekend days in the calendar.
        call_days (list): The list of call days in the calendar.
        region (str): The region for which holidays are loaded.
    """
    def __init__(self, start_date: date, end_date: date, region: str, holidays: List[date] = None):
        self.start_date = start_date
        self.end_date = end_date
        self.region = region
        self.holidays = holidays if holidays else self.load_holidays()
        self.working_days = self.get_working_days()
        self.weekend_days = self.get_weekend_days()
        self.call_days = self.get_call_days()

    @classmethod
    def create_calendar(cls, start_date: date, end_date: date, region: str):
        """
        Creates a calendar with dynamically loaded holidays based on the selected region.
        """
        return cls(start_date, end_date, region)

    def load_holidays(self) -> List[date]:
        """
        Dynamically loads holidays based on the selected region using the `holidays` package.
        """
        region_holidays = []
        for year in range(self.start_date.year, self.end_date.year + 1):
            if self.region == 'Canada/QC':
                region_holidays.extend(holidays.CA(prov='QC', years=year))
            elif self.region == 'Canada/ON':
                region_holidays.extend(holidays.CA(prov='ON', years=year))
            elif self.region == 'USA/CA':
                region_holidays.extend(holidays.US(state='CA', years=year))
            elif self.region == 'USA/NY':
                region_holidays.extend(holidays.US(state='NY', years=year))
            else:
                raise ValueError(f"Unsupported region: {self.region}")
        return [holiday for holiday in region_holidays if self.start_date <= holiday <= self.end_date]

    def get_working_days(self) -> List[date]:
        """
        Returns a list of working days, excluding weekends and holidays.
        """
        working_days = []
        current_date = self.start_date
        while current_date <= self.end_date:
            if current_date.weekday() < 5 and current_date not in self.holidays:
                working_days.append(current_date)
            current_date += timedelta(days=1)
        return working_days

    def get_weekend_days(self) -> List[date]:
        """
        Returns a list of weekend days.
        """
        weekend_days = []
        current_date = self.start_date
        while current_date <= self.end_date:
            if current_date.weekday() >= 5:
                weekend_days.append(current_date)
            current_date += timedelta(days=1)
        return weekend_days

    def get_call_days(self) -> List[date]:
        """
        Returns a list of call days, which is the union of weekend days and holidays.
        """
        return sorted(set(self.weekend_days) | set(self.holidays))

    def add_holiday(self, holiday: date):
        """
        Adds a holiday to the calendar.
        """
        if holiday not in self.holidays:
            self.holidays.append(holiday)
            self.holidays.sort()
            if holiday.weekday() < 5:  # If the holiday is a weekday
                self.working_days.remove(holiday)
            self.call_days = self.get_call_days()

    def remove_holiday(self, holiday: date):
        """
        Removes a holiday from the calendar.
        """
        if holiday in self.holidays:
            self.holidays.remove(holiday)
            if holiday.weekday() < 5:  # If the holiday is a weekday
                self.working_days.append(holiday)
                self.working_days.sort()
            self.call_days = self.get_call_days()

    def show_non_weekend_holidays(self):
        """
        Prints all holidays that are not weekends.
        """
        non_weekend_holidays = [holiday for holiday in self.holidays if holiday.weekday() < 5]
        print("Non-weekend Holidays:", non_weekend_holidays)
        return non_weekend_holidays

    def determine_periods(self) -> Dict[str, List[Dict[str, Any]]]:
        periods = defaultdict(list)
        current_date = self.start_date
        previous_call_period = []
        added_call_periods = set()  # To keep track of added call periods

        while current_date <= self.end_date:
            week_start = current_date - timedelta(days=current_date.weekday())
            week_end = week_start + timedelta(days=6)
            week_days = [week_start + timedelta(days=i) for i in range(7) if
                         week_start + timedelta(days=i) <= self.end_date]

            # Determine main periods (consecutive working days)
            main_period = []
            for day in week_days:
                if day in self.working_days:
                    main_period.append(day)
                else:
                    if main_period:
                        periods[week_start.isoformat()].append({'type': 'MAIN', 'days': main_period})
                        main_period = []
            if main_period:
                periods[week_start.isoformat()].append({'type': 'MAIN', 'days': main_period})

            # Determine call periods (consecutive call days)
            call_period = previous_call_period
            for day in week_days:
                if day in self.call_days:
                    call_period.append(day)
                else:
                    if call_period:
                        self._add_call_periods(periods, week_start, call_period, added_call_periods)
                        call_period = []
            if call_period:
                self._add_call_periods(periods, week_start, call_period, added_call_periods)
                previous_call_period = call_period
            else:
                previous_call_period = []

            current_date = week_end + timedelta(days=1)

        return periods

    def _add_call_periods(self, periods, week_start, call_period, added_call_periods):
        if call_period[0].weekday() < 5:  # If the first call day is a weekday, adjust the week_start
            week_start = call_period[0] - timedelta(days=call_period[0].weekday())

        if len(call_period) >= 4:
            mid_point = len(call_period) // 2
            self._add_single_call_period(periods, week_start, call_period[:mid_point], added_call_periods)
            self._add_single_call_period(periods, week_start, call_period[mid_point:], added_call_periods)
        else:
            self._add_single_call_period(periods, week_start, call_period, added_call_periods)

    def _add_single_call_period(self, periods, week_start, call_period, added_call_periods):
        call_period_start = call_period[0].isoformat()
        if call_period_start not in added_call_periods:
            periods[week_start.isoformat()].append({'type': 'CALL', 'days': call_period})
            added_call_periods.add(call_period_start)

    def save_calendar(self, filename: str):
        """
        Saves the calendar's state to a JSON file.

        Args:
            filename (str): The name of the file to save the calendar state.
        """
        calendar_state = {
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'region': self.region,
            'holidays': [holiday.isoformat() for holiday in self.holidays],
            'working_days': [day.isoformat() for day in self.working_days],
            'weekend_days': [day.isoformat() for day in self.weekend_days],
            'call_days': [day.isoformat() for day in self.call_days]
        }
        with open(filename, 'w') as f:
            json.dump(calendar_state, f, indent=2)

    @classmethod
    def load_calendar(cls, filename: str):
        """
        Loads the calendar's state from a JSON file.

        Args:
            filename (str): The name of the file to load the calendar state from.

        Returns:
            Calendar: An instance of the Calendar class with the loaded state.
        """
        with open(filename, 'r') as f:
            calendar_state = json.load(f)

        start_date = date.fromisoformat(calendar_state['start_date'])
        end_date = date.fromisoformat(calendar_state['end_date'])
        region = calendar_state['region']
        holidays = [date.fromisoformat(day) for day in calendar_state['holidays']]

        calendar = cls(start_date, end_date, region, holidays)
        calendar.working_days = [date.fromisoformat(day) for day in calendar_state['working_days']]
        calendar.weekend_days = [date.fromisoformat(day) for day in calendar_state['weekend_days']]
        calendar.call_days = [date.fromisoformat(day) for day in calendar_state['call_days']]

        return calendar

    def preview_periods(self, periods):
        def format_date_range(dates):
            if len(dates) == 1:
                return dates[0].strftime("%b %d")
            elif len(dates) == 2:
                return f"{dates[0].strftime('%b %d')} - {dates[1].strftime('%b %d')}"
            else:
                return f"{dates[0].strftime('%b %d')} - {dates[-1].strftime('%b %d')}"

        for week_start, week_periods in sorted(periods.items()):
            week_start_date = date.fromisoformat(week_start)
            week_end_date = week_start_date + timedelta(days=6)
            print(f"\nWeek: {week_start_date.strftime('%b %d')} - {week_end_date.strftime('%b %d')}:")

            for period in week_periods:
                period_type = period['type']
                days = period['days']
                print(f"  {period_type}: {format_date_range(days)} ({len(days)} days)")




