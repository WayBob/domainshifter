# server.py in domainshifter/mcp_servers/remote_file_explorer/
import os
import pathlib
import re
import subprocess
import logging
from typing import List
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

# --- Pydantic Models for Structured Tool Outputs ---

class PathContents(BaseModel):
    """Represents the contents of a path on the remote server."""
    subfolders: List[str] = Field(..., description="A list of immediate subfolder names.")
    image_files: List[str] = Field(..., description="A list of image file names in the directory.")

class FileDownloadResult(BaseModel):
    """Represents the result of a remote file download operation."""
    success: bool = Field(..., description="Indicates whether the file was downloaded successfully.")
    local_path: str = Field(..., description="The absolute local path where the file was saved.")
    message: str = Field(..., description="A message describing the result of the download operation.")


def sh_quote(s):
    """Helper for shell quoting."""
    return "'" + s.replace("'", "'\\''") + "'"

def create_app():
    """Creates and configures the FastMCP application."""
    PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
    LOCAL_DEMO_DIR = PROJECT_ROOT / "demo"
    REMOTE_HOST = "tailscale_dummy_host"
    REMOTE_USER = "dummy_user"
    REMOTE_BASE_DEMO_PATH = "/path/to/remote/demo"
    
    app = FastMCP("RemoteFileExplorer")

    def _execute_remote_ssh_command(command: str) -> tuple[bool, str]:
        full_ssh_command = ["ssh", f"{REMOTE_USER}@{REMOTE_HOST}", command]
        logging.info(f"Executing remote SSH command: {' '.join(full_ssh_command)}")
        try:
            process = subprocess.run(
                full_ssh_command, capture_output=True, text=True, check=False, timeout=30
            )
            if process.returncode == 0:
                logging.info(f"Remote command successful. Output:\\n{process.stdout.strip()}")
                return True, process.stdout.strip()
            else:
                error_msg = f"Error (code {process.returncode}): {process.stderr.strip()}"
                logging.error(f"Remote command failed: {error_msg}")
                return False, error_msg
        except Exception as e:
            logging.error(f"An unexpected error occurred during SSH execution: {str(e)}")
            return False, f"An unexpected error occurred during SSH execution: {str(e)}"

    def _scp_remote_to_local(remote_file_full_path: str, local_file_full_path: str) -> tuple[bool, str]:
        scp_command = ["scp", f"{REMOTE_USER}@{REMOTE_HOST}:{remote_file_full_path}", local_file_full_path]
        logging.info(f"Executing SCP command: {' '.join(scp_command)}")
        try:
            os.makedirs(os.path.dirname(local_file_full_path), exist_ok=True)
            process = subprocess.run(
                scp_command, capture_output=True, text=True, check=False, timeout=60
            )
            if process.returncode == 0:
                logging.info(f"File successfully downloaded to {local_file_full_path}")
                return True, f"File successfully downloaded to {local_file_full_path}"
            else:
                error_msg = f"SCP Error (code {process.returncode}): {process.stderr.strip()}"
                logging.error(f"SCP failed: {error_msg}")
                return False, error_msg
        except Exception as e:
            logging.error(f"An unexpected error occurred during SCP: {str(e)}")
            return False, f"An unexpected error occurred during SCP: {str(e)}"

    def _build_safe_remote_path(sub_path: str) -> tuple[str | None, str | None]:
        """
        Safely joins the base remote path with a sub_path provided by the LLM.
        Prevents path traversal and ensures the path is within the allowed directory.
        This version avoids using resolve() to prevent local path interpretation.
        Returns (safe_path, error_message).
        """
        # Use os.path.normpath to clean up paths like 'a/../b' -> 'b'
        # and handle redundant slashes.
        base_path = os.path.normpath(REMOTE_BASE_DEMO_PATH)
        
        # Combine the base path and the sub-path
        # os.path.join handles leading slashes on sub_path correctly on POSIX systems,
        # but we can be extra safe by removing it.
        clean_sub_path = sub_path.lstrip('/')
        target_path = os.path.normpath(os.path.join(base_path, clean_sub_path))
        
        # Security check: Ensure the final path starts with the base path.
        # This is a robust way to prevent path traversal attacks ('..').
        if not target_path.startswith(base_path):
            return None, f"Error: Invalid sub_path '{sub_path}'. Path construction leads outside the designated remote demo directory."
            
        return target_path, None

    @app.tool(description="View the directory tree structure of a specified path on the remote demo server (directories only).")
    def view_remote_directory_tree(sub_path: str = "") -> str:
        """Views the directory tree on the remote server."""
        logging.info(f"Calling tool: view_remote_directory_tree | Parameters: sub_path='{sub_path}'")
        
        target_path_on_remote, error = _build_safe_remote_path(sub_path)
        if error:
            return error
        
        command_to_execute = f"cd {sh_quote(target_path_on_remote)} && find . -type d -print | sed -e 's;[^/]*/;|____;g;s;____|; |----;g'"
        success, output = _execute_remote_ssh_command(command_to_execute)
        return output if success else f"Failed to get remote directory tree structure: {output}"

    @app.tool(description="List all subfolders (top-level) and image files within a specified path on the remote demo server.")
    def list_remote_path_contents(sub_path: str = "") -> PathContents:
        """Lists contents of a remote directory."""
        logging.info(f"Calling tool: list_remote_path_contents | Parameters: sub_path='{sub_path}'")
        
        target_path_on_remote, error = _build_safe_remote_path(sub_path)
        if error:
            return PathContents(subfolders=[], image_files=[f"Error: {error}"])
        
        # More robust command to handle cases with no results gracefully
        command_to_execute = (
            f"cd {sh_quote(target_path_on_remote)} && "
            "echo 'SUBFOLDERS_START' && find . -mindepth 1 -maxdepth 1 -type d -printf '%f\\n' && echo 'SUBFOLDERS_END' && "
            "echo 'IMAGE_FILES_START' && find . -maxdepth 1 -type f \\( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.gif' \\) -printf '%f\\n' && echo 'IMAGE_FILES_END'"
        )
        success, output = _execute_remote_ssh_command(command_to_execute)
        
        if not success:
            return PathContents(subfolders=[], image_files=[f"Failed to list contents: {output}"])

        # Parse the output using markers
        try:
            subfolders_str = re.search(r"SUBFOLDERS_START\n(.*?)\nSUBFOLDERS_END", output, re.DOTALL).group(1)
            image_files_str = re.search(r"IMAGE_FILES_START\n(.*?)\nIMAGE_FILES_END", output, re.DOTALL).group(1)
            
            subfolders = subfolders_str.strip().split('\\n') if subfolders_str.strip() else []
            image_files = image_files_str.strip().split('\\n') if image_files_str.strip() else []
            
            return PathContents(subfolders=subfolders, image_files=image_files)
        except Exception as e:
            logging.error(f"Error parsing remote command output: {e}\\nOutput was:\\n{output}")
            return PathContents(subfolders=[], image_files=[f"Error parsing remote output: {e}"])


    @app.tool(description="Download a specified image file from the remote demo server to a corresponding local demo subfolder.")
    def download_remote_image(remote_file_relative_path: str) -> FileDownloadResult:
        """Downloads a remote image file."""
        logging.info(f"Calling tool: download_remote_image | Parameters: remote_file_relative_path='{remote_file_relative_path}'")
        
        if remote_file_relative_path.startswith('/') or '..' in remote_file_relative_path:
            return FileDownloadResult(success=False, local_path="", message="Error: Invalid path. Must be a relative path.")

        remote_full_path, error = _build_safe_remote_path(remote_file_relative_path)
        if error:
            return FileDownloadResult(success=False, local_path="", message=error)

        parts = pathlib.Path(remote_file_relative_path).parts
        if not parts:
            return FileDownloadResult(success=False, local_path="", message="Error: remote_file_relative_path cannot be empty.")
        
        filename = parts[-1]
        
        local_save_dir = LOCAL_DEMO_DIR.joinpath(*parts[:-1])
        local_full_file_path = local_save_dir / filename
        abs_local_path = str(local_full_file_path.resolve())

        try:
            os.makedirs(local_save_dir, exist_ok=True)
            logging.info(f"Ensured local directory exists: {local_save_dir}")
        except OSError as e:
            logging.error(f"Error creating local directory {local_save_dir}: {e}")
            return FileDownloadResult(success=False, local_path="", message=f"Error creating local directory: {e}")

        logging.info(f"Attempting to download remote '{remote_full_path}' to local '{abs_local_path}'")
        success, message = _scp_remote_to_local(remote_full_path, str(local_full_file_path))
        
        return FileDownloadResult(
            success=success,
            local_path=abs_local_path if success else "",
            message=message
        )

    return app

def main():
    """Main entry point to run the server."""
    # All logging configurations have been removed to ensure silent operation.
    app = create_app()
    app.run(transport="stdio")

if __name__ == "__main__":
    main() 