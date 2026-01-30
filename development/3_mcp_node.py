import asyncio
import pprint

from langchain_core.messages import HumanMessage, AnyMessage
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# --- IMPORTS FOR YOUR CUSTOM FRAMEWORK ---
from src.orin_ai_crm.core.alpha_flow import FlowBuilder
# Your provided MCPAgentNode logic (Assuming it's imported from your nodes module)
# from src.orin_ai_crm.core.agents.nodes import MCPAgentNode
from src.orin_ai_crm.core.models.states import CRMState

async def run_tutorial():
    # 1. Setup MCP Server Parameters (Stdio transport)
    server_params = StdioServerParameters(
        command="python",
        args=["development/3_mcp_server.py"],
    )

    # 2. Open the connection to the MCP Server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            
            # 3. Define the Flow Dictionary
            # Note: We pass the active 'session' into the node's args
            flow_dict = {
                "flow_id": "whatsapp_agent_flow",
                "nodes": [
                    {
                        "name": "start",
                        "node": "start",
                        "to": ["crm_agent"]
                    },
                    {
                        "name": "crm_agent",
                        "node": "mcp_node",
                        "args": {
                            "mcp_client": session,
                            "system_prompt": "You are a WhatsApp CRM assistant, use tools to help answering user.If a tool returns a 'Server error', please try the call again up to 3 times before reporting the failure to the user.",
                            "recursion_limit": 10,
                        },
                        "to": ["end"]
                    }
                ]
            }

            # 4. Build the Agent
            builder = FlowBuilder(flow_dict)
            builder.state_class = CRMState
            agent_graph = builder.build()

            # 5. Run the Graph
            input_state = {
                "messages": [HumanMessage(content="Is Alice in our WhatsApp database?")]
            }

            final_state = input_state.copy()
            
            print("--- Executing MCP Agent Node ---")
            async for chunk in agent_graph.astream(input_state):
                for node, values in chunk.items():
                    print(f"\n>> Update from node: {node}")
                    final_state.update(values)
                    if "messages" in values:
                        # Displaying the response
                        msg = values["messages"]
                        if isinstance(msg, list):
                            msg[-1].pretty_print()
                        else:
                            msg.pretty_print()
            
            # 6. Print the Final State
            print("\n" + "="*30)
            print("FINAL CONSOLIDATED STATE")
            print("="*30)

            # This will print the entire CRMState dictionary
            pprint.pprint(final_state)
if __name__ == "__main__":
    asyncio.run(run_tutorial())