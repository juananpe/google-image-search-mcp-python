import os
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
from typing import List, Dict, Any
from api import search_images, download_image, calculate_relevance_score
from models import ImageSearchResult

# Load environment variables
load_dotenv()

# Validate API key
if not os.getenv("SERP_API_KEY"):
    print("[Error] Missing SERP_API_KEY in environment variables")
    exit(1)

# Create MCP server
mcp = FastMCP("google-image-search")


@mcp.tool()
async def search_images_tool(query: str, limit: int = 10) -> Dict[str, Any]:
    """
    Search for images using Google Image Search

    Args:
        query: The search query for finding images
        limit: Maximum number of results to return (default: 10)

    Returns:
        Dictionary containing the search results
    """
    try:
        print(
            f"[Tool] Executing search_images with query: '{query}', limit: {limit}")
        results = await search_images(query, limit)

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Found {len(results)} images for query '{query}':"
                },
                {
                    "type": "text",
                    "text": str(results)
                }
            ]
        }
    except Exception as error:
        print(f"[Error] search_images failed: {error}")
        return {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": f"Failed to search for images: {str(error)}"
                }
            ]
        }


@mcp.tool()
async def download_image_tool(image_url: str, output_path: str, filename: str) -> Dict[str, Any]:
    """
    Download an image to a local directory

    Args:
        image_url: URL of the image to download
        output_path: Directory path where the image should be saved
        filename: Filename for the downloaded image (including extension)

    Returns:
        Dictionary containing the download result
    """
    try:
        print(f"[Tool] Executing download_image for URL: {image_url}")
        saved_path = await download_image(image_url, output_path, filename)

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Image successfully downloaded to: {saved_path}"
                }
            ]
        }
    except Exception as error:
        print(f"[Error] download_image failed: {error}")
        return {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": f"Failed to download image: {str(error)}"
                }
            ]
        }


@mcp.tool()
async def analyze_images_tool(search_results: List[Dict[str, Any]], criteria: str) -> Dict[str, Any]:
    """
    Analyze image search results to find the most relevant ones

    Args:
        search_results: Array of image search results to analyze
        criteria: Criteria for selecting the best images (e.g., 'professional', 'colorful', etc.)

    Returns:
        Dictionary containing the analysis results
    """
    try:
        print(f"[Tool] Executing analyze_images with criteria: '{criteria}'")

        # Calculate relevance scores and add recommendations
        analyzed_results = []
        for img in search_results:
            img_result = ImageSearchResult(**img)
            img_result["relevanceScore"] = calculate_relevance_score(
                img_result, criteria)
            analyzed_results.append(img_result)

        # Sort by relevance score
        analyzed_results.sort(key=lambda x: x.get(
            "relevanceScore", 0), reverse=True)

        # Add recommendations based on ranking
        for i, img in enumerate(analyzed_results):
            img["recommendation"] = (
                "Highly recommended" if i < 3
                else "Recommended" if i < 6
                else "Standard option"
            )

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Analyzed {len(analyzed_results)} images based on criteria: '{criteria}'"
                },
                {
                    "type": "text",
                    "text": str(analyzed_results)
                }
            ]
        }
    except Exception as error:
        print(f"[Error] analyze_images failed: {error}")
        return {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": f"Failed to analyze images: {str(error)}"
                }
            ]
        }

if __name__ == "__main__":
    mcp.run(transport="stdio")
