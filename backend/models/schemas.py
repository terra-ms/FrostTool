from pydantic import BaseModel


class AvailableDatesResponse(BaseModel):
    dates: list[str]


class ColorscaleResponse(BaseModel):
    min_value: float
    max_value: float
    mean_value: float
    units: str


class CellValueResponse(BaseModel):
    value: float
    lat: float
    lon: float
    date: str


class TimeseriesDataPoint(BaseModel):
    date: str
    value: float


class TimeseriesResponse(BaseModel):
    lat: float
    lon: float
    start_date: str
    end_date: str
    data: list[TimeseriesDataPoint]
    units: str


class HealthResponse(BaseModel):
    status: str


class CropInfo(BaseModel):
    name: str
    display_name: str


class CropsResponse(BaseModel):
    crops: list[CropInfo]


class GDDColorscaleResponse(BaseModel):
    min_value: int
    max_value: int


class GDDAvailableYearsResponse(BaseModel):
    years: list[int]
    min_year: int
    max_year: int


class ContinentBounds(BaseModel):
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


class ContinentDetail(BaseModel):
    bounds: ContinentBounds
