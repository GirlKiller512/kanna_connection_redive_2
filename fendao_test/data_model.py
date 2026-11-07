from typing import Any, List, TypedDict

from pydantic import BaseModel, field_validator, model_validator


class DetailItem(BaseModel):
    name: str
    value: int

    @model_validator(mode="before")
    @classmethod
    def unpack_pair(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            name, number = value
            return {"name": name, "value": number}
        return value


class VideoItem(BaseModel):
    text: str
    url: str
    image: List[str]
    note: str

    @field_validator("image", mode="before")
    @classmethod
    def extract_image_urls(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            return value
        return [
            image.get("url", image) if isinstance(image, dict) else image
            for image in value
        ]


class HomeworkItem(BaseModel):
    id: int
    sn: str
    unit: List[int]
    damage: int
    auto: int
    remain: int
    info: str
    video: List[VideoItem]


class JoyshowItem(BaseModel):
    img: str
    msg: str
    width: int
    height: int


class DataItem(BaseModel):
    id: str
    stage: int
    rate: float
    info: str
    detail: List[DetailItem]
    part: List[str]
    homework: List[HomeworkItem]
    joyshow: List[JoyshowItem]


class HomeWorkData(BaseModel):
    status: int
    data: List[DataItem]


class VideoDictItem(TypedDict):
    text: str
    url: str
    image: List[str]
    note: str


class HomeWorkDictItem(TypedDict):
    unit: List[int]
    damage: int
    info: str
    video_link: List[VideoDictItem]
