# Google Image Search MCP

A Python-based MCP (Model Context Protocol) server that provides tools for searching, downloading, and analyzing images using Google Image Search.

## Features

- Search for images using Google Image Search API
- Download images to local storage
- Analyze image search results based on custom criteria
- Calculate relevance scores for images
- Provide recommendations based on image quality and relevance

## Installation

1. Clone the repository
2. Initialize the project with [uv](https://github.com/astral-sh/uv): (just once)
   ```bash
   uv init
   ```
3. Create a virtual environment:
   ```bash
   uv venv
   ```
3. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```
4. Install dependencies:
   (en Linux/macOS)
   ```powershell
   .venv\Scripts\activate
   ```

5. Install dependencies:
   ```bash
   uv pip install -r pyproject.toml
   ```
   (en Windows)
   ```powershell
   .\.venv\Scripts\activate
   uv pip install -r pyproject.toml
   ```
6. Create a `.env` file with your SerpAPI key:
   ```
   SERP_API_KEY=your_api_key_here
   ```
7. Create the `temp` directory:
   ```bash
   mkdir temp
   ```

## Usage

Run the server:

```bash
uv run main.py
```

Test the MCP server with inspector:

```bash
npx @modelcontextprotocol/inspector uv run main.py
```


In Windows+Windsurf:

```
{
  "mcpServers": {
    "search-images": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\Users\\YOURUSERNAME\\google-image-search-mcp-python",
        "run",
        "main.py"
      ]
    }
  }
}
```

The server provides the following tools:

1. `search_images_tool`: Search for images using Google Image Search

   - Parameters:
     - `query`: The search query for finding images
     - `limit`: Maximum number of results to return (default: 10)

2. `download_image_tool`: Download an image to a local directory

   - Parameters:
     - `image_url`: URL of the image to download
     - `output_path`: Directory path where the image should be saved
     - `filename`: Filename for the downloaded image (including extension)

3. `analyze_images_tool`: Analyze image search results to find the most relevant ones
   - Parameters:
     - `search_results`: Array of image search results to analyze
     - `criteria`: Criteria for selecting the best images (e.g., 'professional', 'colorful', etc.)

## Example

```python
# Search for images
results = await search_images_tool("cute puppies", limit=5)

# Download an image
saved_path = await download_image_tool(
    image_url="https://example.com/image.jpg",
    output_path="./images",
    filename="puppy.jpg"
)

# Analyze search results
analysis = await analyze_images_tool(
    search_results=results,
    criteria="high quality professional"
)
```

## Error Handling

The tools provide detailed error messages when something goes wrong. All errors are logged to stderr and returned in a structured format with an `isError` flag.

## Dependencies

- mcp-server: For MCP server functionality
- python-dotenv: For environment variable management
- aiohttp: For async HTTP requests
