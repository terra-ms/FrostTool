from datetime import date


class DatasetNotFoundError(Exception):
    def __init__(self, date_obj: date) -> None:
        self.date = date_obj
        super().__init__(f"No NetCDF file found for date {date_obj}")


class VariableNotFoundError(Exception):
    def __init__(self, variable: str, path: str) -> None:
        self.variable = variable
        self.path = path
        super().__init__(f"Variable '{variable}' not found in {path}")


class InvalidTimeIndexError(Exception):
    def __init__(self, index: int, max_index: int) -> None:
        self.index = index
        self.max_index = max_index
        super().__init__(f"Time index {index} out of range [0, {max_index}]")
