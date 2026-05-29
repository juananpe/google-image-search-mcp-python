from typing import Optional, TypedDict


class ImageSearchResult(TypedDict):
    position: int
    thumbnail: str
    source: str
    title: str
    link: str
    original: str
    is_product: bool
    size: Optional[str]
    original_width: Optional[int]
    original_height: Optional[int]
