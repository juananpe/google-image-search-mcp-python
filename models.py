from typing import List, Optional, TypedDict

class ImageSearchResult(TypedDict):
    position: int
    thumbnail: str
    source: str
    title: str
    link: str
    original: str
    is_product: bool
    size: Optional[str]
    width: Optional[int]
    height: Optional[int]
    relevanceScore: Optional[float]
    recommendation: Optional[str]

class SearchMetadata(TypedDict):
    id: str
    status: str
    json_endpoint: str
    created_at: str
    processed_at: str
    google_images_url: str
    raw_html_file: str
    total_time_taken: float

class SearchParameters(TypedDict):
    engine: str
    q: str
    google_domain: str
    ijn: str
    device: str

class MenuItem(TypedDict):
    position: int
    title: str
    link: str
    serpapi_link: str

class SearchInformation(TypedDict):
    image_results_state: str
    query_displayed: str
    menu_items: List[MenuItem]

class SearchResponse(TypedDict):
    search_metadata: SearchMetadata
    search_parameters: SearchParameters
    search_information: SearchInformation
    images_results: List[ImageSearchResult] 