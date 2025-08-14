# domainshifter/mcp_client_manager.py
import json
import pathlib
import asyncio
from typing import Dict, List, Tuple
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient


# Define paths relative to this file
current_dir = pathlib.Path(__file__).resolve().parent
MCP_JSON_PATH = current_dir / "mcp.json"

class RobustMCPClient:
    """
    A robust MCP client that can gracefully handle server connection failures
    """
    def __init__(self, server_configs: Dict):
        self.server_configs = server_configs
        self.available_tools = []
        self.failed_servers = []
        self.successful_servers = []
    
    async def get_tools_with_fallback(self) -> Tuple[List[BaseTool], List[str], List[str]]:
        """
        Try to load tools from each server, recording successful and failed servers
        Returns: (available tools list, successful servers list, failed servers list)
        """
        all_tools = []
        successful_servers = []
        failed_servers = []
        
        for server_name, config in self.server_configs.items():
            try:
                print(f"  - Attempting to connect to server: {server_name}...")
                
                # Create temporary client for single server
                single_server_config = {server_name: config}
                temp_client = MultiServerMCPClient(single_server_config)
                
                # Set shorter timeout to avoid long waits
                tools = await asyncio.wait_for(temp_client.get_tools(), timeout=10.0)
                
                all_tools.extend(tools)
                successful_servers.append(server_name)
                print(f"    ✅ Successfully connected to {server_name}, got {len(tools)} tools")
                
            except asyncio.TimeoutError:
                failed_servers.append(server_name)
                print(f"    ❌ Connection to {server_name} timed out")
                
            except Exception as e:
                failed_servers.append(server_name)
                print(f"    ❌ Connection to {server_name} failed: {str(e)[:100]}...")
        
        self.available_tools = all_tools
        self.successful_servers = successful_servers
        self.failed_servers = failed_servers
        
        return all_tools, successful_servers, failed_servers

def get_mcp_client():
    """
    Load MCP server configurations and return a robust client instance
    """
    # 1. Load and parse the mcp.json file
    if not MCP_JSON_PATH.exists():
        raise FileNotFoundError(f"MCP configuration file not found at: {MCP_JSON_PATH}")
        
    with open(MCP_JSON_PATH, 'r') as f:
        config_data = json.load(f)
    
    server_configs = config_data.get("mcpServers", {})
    if not server_configs:
        raise ValueError("No 'mcpServers' found in mcp.json")

    # 2. Dynamically replace {PROJECT_ROOT} placeholder
    project_root = current_dir
    for server_name, config in server_configs.items():
        if "command" in config and isinstance(config["command"], str):
            config["command"] = config["command"].replace("{PROJECT_ROOT}", str(project_root))
        
        if "args" in config and isinstance(config["args"], list):
            config["args"] = [
                arg.replace("{PROJECT_ROOT}", str(project_root)) if isinstance(arg, str) else arg
                for arg in config["args"]
            ]
        
        if "env" in config and isinstance(config["env"], dict):
            for key, value in config["env"].items():
                if isinstance(value, str):
                    config["env"][key] = value.replace("{PROJECT_ROOT}", str(project_root))

    # 3. Return robust client
    return RobustMCPClient(server_configs)

if __name__ == '__main__':
    # Example usage and testing
    print("--- Testing Robust MCP Client Manager ---")
    try:
        client = get_mcp_client()
        print(f"✅ Successfully created RobustMCPClient with {len(client.server_configs)} servers configured.")
        
        # Test tool loading
        async def test_tools():
            print("\n--- Testing Tool Loading ---")
            tools, successful, failed = await client.get_tools_with_fallback()
            print("\n📊 Connection Results:")
            print(f"  - Successfully connected servers: {len(successful)}")
            for server in successful:
                print(f"    ✅ {server}")
            print(f"  - Failed servers: {len(failed)}")
            for server in failed:
                print(f"    ❌ {server}")
            print(f"  - Total available tools: {len(tools)}")
        
        import asyncio
        asyncio.run(test_tools())
    except Exception as e:
        print(f"❌ Failed to create MCP client: {e}") 