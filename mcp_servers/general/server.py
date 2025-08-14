# server.py in domainshifter/mcp_servers/general/
from datetime import datetime
from dotenv import load_dotenv
import httpx
import json
import os
import pathlib
from typing import List
from bs4 import BeautifulSoup
import logging
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

# --- Pydantic Models for Structured Tool Outputs ---

class DocSearchResult(BaseModel):
    """Represents a single search result from the get_docs tool."""
    title: str = Field(..., description="The title of the document.")
    link: str = Field(..., description="The direct URL to the document.")
    summary: str = Field(..., description="A short summary of the document content.")
    content: str = Field(..., description="The full, cleaned content of the document.")

class FileSaveResult(BaseModel):
    """Represents the result of a file save operation."""
    success: bool = Field(..., description="Indicates whether the file was saved successfully.")
    file_path: str = Field(..., description="The absolute path to the saved file.")
    message: str = Field(..., description="A message describing the result of the operation.")


def create_app():
    # Define project root assuming this file is in domainshifter/mcp_servers/general/
    PROJECT_ROOT_GENERAL_SERVER = pathlib.Path(__file__).resolve().parent.parent.parent

    # Configure logging to write tool usage and arguments to a file
    logging.basicConfig(filename="mcp_tool.log", level=logging.INFO, format='%(asctime)s %(message)s')

    load_dotenv()

    app = FastMCP("MultiTool")
    
    LOCAL_DOCS_DIR = str(PROJECT_ROOT_GENERAL_SERVER / "doc")
    OUTPUT_DIR = str(PROJECT_ROOT_GENERAL_SERVER / "output")

    docs_urls = {
        "langchain": "python.langchain.com/docs",
        "llama-index": "docs.llamaindex.ai/en/stable",
        "openai": "platform.openai.com/docs",
        "electron": "https://www.electronjs.org/docs/latest/",
        "openrouter": "openrouter.ai/docs",
        "langgraph": "https://langchain-ai.github.io/langgraph/tutorials/langgraph-platform/local-server/"
    }

    async def search_web(query: str) -> dict | None:
        payload = json.dumps({"q": query, "num": 2})
        headers = {
            "X-API-KEY": os.getenv("SERPER_API_KEY"),
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://google.serper.dev/search", headers=headers, data=payload, timeout=30.0
                )
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException:
                return {"organic": []}
      
    async def fetch_url(url: str):
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, timeout=30.0)
                soup = BeautifulSoup(response.text, "html.parser")
                for script in soup(["script", "style", "meta", "link", "svg", "path", "nav", "header", "footer"]):
                    script.decompose()
                main_content = soup.find("main") or soup.find("article") or soup.find("div", class_="content") or soup
                text = main_content.get_text(separator="\\n", strip=True)
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                text = "\\n".join(lines)
                if len(text) > 8000:
                    text = text[:8000] + "...\\n[Content too long, truncated]"
                return text
            except httpx.TimeoutException:
                return "Timeout error"
            except Exception as e:
                return f"Error fetching URL: {str(e)}"

    def read_local_file(file_path: str) -> str:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def get_file_path(file_type: str, filename: str) -> str:
        if file_type == "doc":
            return os.path.join(LOCAL_DOCS_DIR, filename)
        else:
            raise ValueError(f"Unknown file type: {file_type}")

    def list_local_docs() -> list:
        try:
            files = []
            if not os.path.exists(LOCAL_DOCS_DIR):
                os.makedirs(LOCAL_DOCS_DIR, exist_ok=True)
            for file in pathlib.Path(LOCAL_DOCS_DIR).glob('**/*'):
                if file.is_file():
                    files.append(f"doc:{str(file.relative_to(LOCAL_DOCS_DIR))}")
            return files
        except Exception as e:
            return [f"Error listing files: {str(e)}"]

    # --- Tool Definitions ---
    
    @app.tool(description="Add two numbers and return the result.")
    def add(a: int, b: int) -> int:
        logging.info(f"Calling tool: add | Parameters: a={a}, b={b}")
        return a + b

    @app.tool(description="Multiply two numbers and return the result.")
    def multiply(a: int, b: int) -> int:
        logging.info(f"Calling tool: multiply | Parameters: a={a}, b={b}")
        return a * b

    @app.tool(description="Get the current time as a formatted string.")
    def get_time() -> str:
        logging.info("Calling tool: get_time | Parameters: None")
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @app.tool(description="Clear the conversation history and return a confirmation message.")
    def clear_history() -> str:
        logging.info("Calling tool: clear_history | Parameters: None")
        return "Conversation history has been cleared."

    @app.tool(description="Search the latest docs for a given query and library. Supports langchain, openai, openrouter, llama-index, electron.")  
    async def get_docs(query: str, library: str) -> List[DocSearchResult]:
        logging.info(f"Calling tool: get_docs | Parameters: query={query}, library={library}")
        if library not in docs_urls:
            # In a real app, you might want a more structured error
            return [DocSearchResult(title="Error", link="", summary="", content=f"Library {library} not supported.")]
        
        search_query = f"site:{docs_urls[library]} {query}"
        results = await search_web(search_query)
        if not results or not results.get("organic"):
            return [DocSearchResult(title="No Results", link="", summary="", content="No search results found.")]
        
        search_results = []
        for result in results["organic"][:2]: # Limit to top 2 results for brevity
            title = result.get("title", "Unknown title")
            link = result.get("link", "")
            if not link:
                continue
            
            content = await fetch_url(link)
            summary = content[:500] + "..." if len(content) > 500 else content
            
            search_results.append(
                DocSearchResult(
                    title=title,
                    link=link,
                    summary=summary,
                    content=content,
                )
            )
        return search_results

    @app.tool(description="List all available documents in the local directory.")
    def list_docs() -> List[str]:
        logging.info("Calling tool: list_docs | Parameters: None")
        try:
            files = []
            if not os.path.exists(LOCAL_DOCS_DIR):
                os.makedirs(LOCAL_DOCS_DIR, exist_ok=True)
            for file in pathlib.Path(LOCAL_DOCS_DIR).glob('**/*'):
                if file.is_file():
                    # Return just the filename, which is simpler and more useful
                    files.append(file.name)
            if not files:
                return ["No local documents found."]
            return files
        except Exception as e:
            return [f"Error listing files: {str(e)}"]

    @app.tool(description="Read a local document from the project's 'doc' directory.")
    def read_local_doc(filename: str):
        logging.info(f"Calling tool: read_local_doc | Parameters: filename={filename}")
        file_type, file_name = filename.split(":", 1) if ":" in filename else ("doc", filename)
        file_path = get_file_path(file_type, file_name)
        if not os.path.abspath(file_path).startswith(os.path.abspath(LOCAL_DOCS_DIR)):
            return f"Security error: Cannot access files outside of {LOCAL_DOCS_DIR}"
        if not os.path.exists(file_path):
            return f"File not found: {filename}"
        return read_local_file(file_path)

    @app.tool(description="Save text content to a Markdown file in the 'output' directory.")
    def save_markdown_file(filename: str, content: str) -> FileSaveResult:
        logging.info(f"Calling tool: save_markdown_file | Parameters: filename={filename}")
        if ".." in filename or "/" in filename or "\\\\" in filename:
            logging.error(f"save_markdown_file: Invalid characters in filename: {filename}")
            return FileSaveResult(
                success=False, 
                file_path="", 
                message="Error: Invalid filename. Filename should not contain path separators."
            )
        try:
            if not os.path.exists(OUTPUT_DIR):
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                logging.info(f"Created output directory: {OUTPUT_DIR}")
        except OSError as e:
            logging.error(f"save_markdown_file: Error creating output directory {OUTPUT_DIR}: {e}")
            return FileSaveResult(success=False, file_path="", message=f"Error: Could not create output directory: {e}")

        file_path = os.path.join(OUTPUT_DIR, filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            abs_path = os.path.abspath(file_path)
            logging.info(f"Successfully saved file to {abs_path}")
            return FileSaveResult(
                success=True,
                file_path=abs_path,
                message=f"Content successfully saved to {abs_path}"
            )
        except IOError as e:
            logging.error(f"save_markdown_file: Error writing file {file_path}: {e}")
            return FileSaveResult(success=False, file_path="", message=f"Error: Could not write to file {filename}: {e}")
        except Exception as e:
            logging.error(f"save_markdown_file: Unexpected error for file {file_path}: {e}")
            return FileSaveResult(success=False, file_path="", message=f"An unexpected error occurred while saving {filename}: {e}")
            
    return app

def main():
    """Main entry point to run the server."""
    app = create_app()
    app.run(transport="stdio")

if __name__ == "__main__":
    main() 