import os
import aiohttp
from pathlib import Path
from typing import List
from models import ImageSearchResult


async def search_images(query: str, limit: int = 10) -> List[ImageSearchResult]:
    """Search for images using the SerpAPI"""
    print(f"[API] Searching for images with query: '{query}'")

    try:
        async with aiohttp.ClientSession() as session:
            params = {
                "q": query,
                "engine": "google_images",
                "api_key": os.getenv("SERP_API_KEY")
            }
            async with session.get("https://serpapi.com/search", params=params) as response:
                response.raise_for_status()
                data = await response.json()

                if not data["images_results"]:
                    raise ValueError("No image results found")

                return data["images_results"][:limit]
    except Exception as error:
        print(f"[Error] Failed to search images: {error}")
        raise


async def download_image(image_url: str, output_path: str, filename: str) -> str:
    """Download an image to the specified directory"""
    print(f"[API] Downloading image from: {image_url}")

    try:
        # Create directory if it doesn't exist
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        full_path = output_dir / filename

        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                response.raise_for_status()
                content = await response.read()

                with open(full_path, "wb") as f:
                    f.write(content)

        print(f"[API] Image downloaded successfully to: {full_path}")
        return str(full_path)
    except Exception as error:
        print(f"[Error] Failed to download image: {error}")
        raise
