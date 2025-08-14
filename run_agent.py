# domainshifter/run_agent.py
import asyncio
import click
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from llm_manager import load_models_from_json, get_llm, create_system_prompt
from mcp_client_manager import get_mcp_client

def print_welcome():
    """Prints the welcome message."""
    print("=" * 55)
    print("🤖 Welcome to the Multi-MCP Server ReAct Agent!")
    print("=" * 55)

def select_model_interactive(models):
    """Interactively prompts the user to select a model."""
    print("\nPlease select a Language Model to use:")
    for i, model in enumerate(models):
        print(f"  {i+1:2d}. {model['name']}")
    
    while True:
        try:
            choice = int(input(f"Enter your choice (1-{len(models)}): "))
            if 1 <= choice <= len(models):
                return models[choice - 1]['id']
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number.")

async def interactive_chat_session(model_id: str, run_self_check: bool):
    """
    Sets up the agent, runs an initial self-check, and enters an
    interactive chat loop with the user.
    """
    print(f"\n🧠 Using model: {model_id}")
    
    # --- Setup (runs once) ---
    try:
        llm = get_llm(model_id)
        print("✅ LLM instance created.")
        
        print("🚀 Initializing MCP client...")
        mcp_client = get_mcp_client()
        
        print("🛠️  Fetching tools from all MCP servers...")
        tools, successful_servers, failed_servers = await mcp_client.get_tools_with_fallback()
        
        # Report connection status
        print("\n📊 MCP Server Connection Status:")
        if successful_servers:
            print(f"  ✅ Successfully connected servers ({len(successful_servers)}):")
            for server in successful_servers:
                print(f"    - {server}")
        
        if failed_servers:
            print(f"  ❌ Failed to connect servers ({len(failed_servers)}):")
            for server in failed_servers:
                print(f"    - {server}")
        
        print(f"\n🛠️  Total available tools: {len(tools)}")
        
        if len(tools) == 0:
            print("⚠️  Warning: No tools available! Agent will only be able to perform basic conversation.")
        
        # Give user a hint if some servers failed
        if failed_servers and successful_servers:
            print("💡 Note: Some MCP servers failed to connect, but the program can still run normally.")
        elif failed_servers and not successful_servers:
            print("⚠️  Warning: All MCP servers failed to connect, Agent will run in basic mode.")

        
        agent_executor = create_react_agent(llm, tools, prompt=create_system_prompt())
        print("🤖 ReAct Agent created successfully.")
        
    except (ValueError, ImportError) as e:
        print(f"❌ Error during setup: {e}")
        return
    except Exception as e:
        import traceback
        print(f"❌ An unexpected error occurred during setup: {e}")
        traceback.print_exc()
        return

    # --- Self-Check on Startup ---
    async def run_direct_tool_check(server_name: str, tool_name: str, test_params: dict = None) -> bool:
        """Directly test a specific tool from a specific server, bypassing Agent."""
        print(f"\n▶️  CHECKING: {server_name} (using {tool_name})...")
        
        try:
            # Create a temporary client for this specific server only
            server_config = mcp_client.server_configs.get(server_name)
            if not server_config:
                print(f"❌ FAIL: Server {server_name} not found in configuration")
                return False
            
            # Create single-server client
            from langchain_mcp_adapters.client import MultiServerMCPClient
            temp_client = MultiServerMCPClient({server_name: server_config})
            
            # Try to get tools from this server with a short timeout
            tools = await asyncio.wait_for(temp_client.get_tools(), timeout=15.0)
            
            # Find the specific tool
            target_tool = None
            for tool in tools:
                if tool.name == tool_name:
                    target_tool = tool
                    break
            
            if not target_tool:
                available_tools = [t.name for t in tools]
                print(f"❌ FAIL: Tool '{tool_name}' not found. Available tools: {available_tools}")
                return False
            
            # Call the tool directly with test parameters
            if test_params is None:
                test_params = {}
            
            result = await target_tool.ainvoke(test_params)
            
            print(f"✅ PASS: {server_name} responded successfully")
            print("  " + "┌" + "─" * 20 + " Direct Tool Output " + "─" * 19 + "┐")
            result_str = str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
            for line in result_str.splitlines():
                print(f"  | {line}")
            print("  " + "└" + "─" * 59 + "┘")
            
            return True
            
        except asyncio.TimeoutError:
            print(f"❌ FAIL: {server_name} connection timed out")
            return False
        except Exception as e:
            print(f"❌ FAIL: {server_name} error: {str(e)[:100]}...")
            return False
    
    async def run_single_check(agent_executor, check_name: str, query: str) -> bool:
        """Helper function to run a single self-check query via Agent (for local tools only)."""
        print(f"\n▶️  CHECKING: {check_name}...")
        try:
            config = {"recursion_limit": 50}
            result = await agent_executor.ainvoke(
                {"messages": [HumanMessage(content=query)]}, config=config
            )
            
            final_content = "No output message found."
            if result and 'messages' in result and result['messages']:
                last_message = result['messages'][-1]
                if hasattr(last_message, 'content'):
                    content = last_message.content
                    if isinstance(content, list):
                        final_content = "\n".join(
                            c.get("text", "") for c in content if "text" in c
                        )
                    else:
                        final_content = str(content)
            
            print(f"✅ PASS: {check_name} completed successfully.")
            print("  " + "┌" + "─" * 20 + " Agent Response " + "─" * 22 + "┐")
            for line in final_content.splitlines():
                print(f"  | {line}")
            print("  " + "└" + "─" * 59 + "┘")

            return True
        except Exception as e:
            print(f"❌ FAIL: {check_name} failed with an error: {e}")
            return False

    if run_self_check:
        print("\n" + "="*20 + " Running Self-Check " + "="*22)
        
        # Define tests for each MCP server with representative tools
        server_tests = [
            {
                "server_name": "general-tool",
                "tool_name": "get_time",
                "test_params": {},
                "description": "Local General Server"
            },
            {
                "server_name": "RemoteFileExplorerService", 
                "tool_name": "list_remote_path_contents",
                "test_params": {"path": "/"},
                "description": "Remote File Explorer"
            },
            {
                "server_name": "amap-maps",
                "tool_name": "maps_weather", 
                "test_params": {"city": "北京"},
                "description": "Amap Maps Service"
            },
            {
                "server_name": "LocalWeatherService",
                "tool_name": "get-weather",
                "test_params": {"location": "Tokyo"},
                "description": "Remote Weather Server"
            },
            {
                "server_name": "StyleTransferService",
                "tool_name": "get_model_info",
                "test_params": {},
                "description": "Remote Style Transfer Server"
            },
            {
                "server_name": "SnwoyGenerationService", 
                "tool_name": "generate_snow",
                "test_params": {"prompt": "snow scene"},
                "description": "Remote Snow Generation Server"
            }
        ]
        
        print(f"📋 Will test {len(server_tests)} MCP servers directly...")
        print("🔧 Each server will be tested with its representative tool...")
        
        # Run direct tool tests in parallel
        test_tasks = [
            run_direct_tool_check(test["server_name"], test["tool_name"], test["test_params"])
            for test in server_tests
        ]
        
        results = await asyncio.gather(*test_tasks, return_exceptions=True)
        
        # Analyze results
        passed_count = 0
        failed_servers = []
        successful_servers = []
        
        for i, (result, test) in enumerate(zip(results, server_tests)):
            if isinstance(result, Exception):
                failed_servers.append(test["server_name"])
                print(f"❌ EXCEPTION: {test['server_name']} - {result}")
            elif result:
                passed_count += 1
                successful_servers.append(test["server_name"])
            else:
                failed_servers.append(test["server_name"])
        
        print(f"\n📊 Direct Server Test Results:")
        print(f"   Successful servers: {passed_count}/{len(server_tests)}")
        for server in successful_servers:
            print(f"     ✅ {server}")
        print(f"   Failed servers: {len(failed_servers)}/{len(server_tests)}")
        for server in failed_servers:
            print(f"     ❌ {server}")
        
        if passed_count == len(server_tests):
            print(f"\n🎉 All MCP servers are operational!")
        elif passed_count > 0:
            print(f"\n⚠️  {passed_count}/{len(server_tests)} servers are working. Agent can operate with available servers.")
        else:
            print(f"\n❌ All MCP servers failed. Agent will run in basic mode.")
        
        print("\n" + "="*20 + " Self-Check Finished " + "="*21)
    elif run_self_check:
        print("\n⚠️  Skipping self-check: Self-check requested but no setup completed")

    # --- Interactive Chat Loop ---
    print("\n" + "="*20 + " Interactive Chat Mode " + "="*21)
    print("🤖 Agent is ready. Type `/model` to switch LLM, or 'quit'/'exit' to end.")
    while True:
        try:
            user_input = input("\n👤 You: ")
            if user_input.lower() in ["quit", "exit"]:
                print("🤖 Goodbye!")
                break
            
            if user_input.lower().strip() == "/model":
                print("\n" + "="*20 + " Switching Model " + "="*25)
                
                # Reload models and prompt user for a new selection
                models = load_models_from_json()
                new_model_id = select_model_interactive(models)
                
                try:
                    # Create a new LLM instance and rebuild the agent
                    llm = get_llm(new_model_id)
                    agent_executor = create_react_agent(llm, tools, prompt=create_system_prompt())
                    model_id = new_model_id  # Update the current model_id
                    print(f"\n✅ Switched model to: {model_id}")
                    print("🤖 Agent is ready with the new model.")
                except Exception as e:
                    print(f"\n❌ Failed to switch model: {e}")
                    print("🤖 Reverting to the previous model.")
                
                print("\n" + "="*20 + " Interactive Chat Mode " + "="*21)
                continue # Restart the loop to wait for the next prompt

            if not user_input.strip():
                continue

            print("\n" + "="*20 + " Agent Execution Starts " + "="*20)
            
            final_answer = ""
            
            # Use a generous recursion limit for complex user-driven tasks.
            config = {"recursion_limit": 150}
            try:
                # According to LangGraph docs, stream_mode="updates" is the
                # standard way to get the output of each step of the agent.
                async for chunk in agent_executor.astream(
                    {"messages": [HumanMessage(content=user_input)]}, 
                    config=config,
                    stream_mode="updates"
                ):
                    # The chunk is a dictionary where the key is the node name
                    # and the value is the output of that node.
                    # We are interested in the final AIMessage from the agent.
                    for key, value in chunk.items():
                        if isinstance(value, dict) and "messages" in value:
                            last_message = value["messages"][-1]
                            if isinstance(last_message, AIMessage):
                                final_answer = last_message.content
            except Exception as e:
                import traceback
                print(f"\n❌ An error occurred during streaming: {e}")
                traceback.print_exc()
            
            finally:
                # Always print the final answer at the end of execution.
                # This ensures that even if there are no tool calls, the direct
                # response from the LLM is displayed to the user.
                if final_answer:
                    print("\n🤖 Assistant:")
                    # Use click.echo to handle different terminal environments better
                    click.echo(final_answer)
                else:
                    # This might happen if the agent failed or produced no output
                    print("\n🤖 Assistant: (No response generated)")
                
                print("\n" + "="*20 + " Agent Execution Ends " + "="*22)

        except KeyboardInterrupt:
            print("\n🤖 Session interrupted by user. Goodbye!")
            break
        except Exception as e:
            import traceback
            print(f"\n❌ An error occurred during the agent workflow: {e}")
            traceback.print_exc()

@click.command()
@click.option('--model', 'model_id', default=None, help="The ID of the model to use (e.g., 'deepseek/deepseek-chat').")
@click.option('--no-self-check', 'disable_self_check', is_flag=True, default=False, help="Disable the initial self-check queries on startup.")
def cli(model_id, disable_self_check):
    """
    A command-line interface for running a ReAct agent with multiple MCP servers.
    """
    print_welcome()
    
    # Load .env file for API keys
    load_dotenv()

    models = load_models_from_json()
    if not models:
        print("❌ Error: Could not load models from models.json.")
        return

    if model_id:
        # Verify the chosen model ID exists
        if not any(m['id'] == model_id for m in models):
            print(f"❌ Error: Model ID '{model_id}' not found in models.json.")
            print("Available model IDs:", [m['id'] for m in models])
            return
    else:
        # Interactive selection if no model is provided via command line
        model_id = select_model_interactive(models)
    
    try:
        # Pass the self_check flag to the session handler (inverted because disable_self_check is a disable flag)
        run_self_check = not disable_self_check
        asyncio.run(interactive_chat_session(model_id, run_self_check))
    finally:
        print("\n✅ Chat session finished.")

if __name__ == "__main__":
    # To run:
    # Interactive mode: python domainshifter/run_agent.py
    # To skip the self-check: python domainshifter/run_agent.py --no-self-check
    cli() 