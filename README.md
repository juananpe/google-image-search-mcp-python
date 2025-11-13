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
2. Install [uv](https://github.com/astral-sh/uv) _(just once, if needed)_
3. Create a virtual environment: _(just once)_
   ```bash
   uv venv
   ```
3. Activate the virtual environment:

Linux/macOS:

   ```bash
   source .venv/bin/activate
   ```
   Windows:

   ```powershell
   .venv\Scripts\activate
   ```

4. Install dependencies:

Linux/macOS:

   ```bash
   uv pip install -r requirements.txt
   ```

Windows:
   ```powershell
   uv pip install -r requirements.txt
   ```
5. Create a `.env` file with your SerpAPI key:
(Get your key here: https://serpapi.com/dashboard)
   ```
   SERP_API_KEY=your_api_key_here
   ```

## Usage

You can either run the server:

```bash
uv run main.py
```

or test the MCP server with inspector:

```bash
npx @modelcontextprotocol/inspector uv run main.py
```

Run the server:

```bash
uv run main.py
```


In VSCode, add this MCP server configuration to your `mcp-servers.json` file:

```
{
  "servers": {
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

On a Mac. 

First locate where your uv script is located. For example:

```
# which uv
/opt/homebrew/Caskroom/mambaforge/base/bin/uv
```

Then apply the location of the uv script to cursor, windsurf, claude, etc
```
{
   "mcpServers": {
    "search-images": {
      "command": "/opt/homebrew/Caskroom/mambaforge/base/bin/uv",
      "args": [
        "--directory",
        "/opt/agents/google-image-search-mcp-python",
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

## Examples

### Prompt:

   > use your search images tool to search for 5 images about "cute cats", analyze them and download the best 3 ones in ./gatitos/

### Code

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
