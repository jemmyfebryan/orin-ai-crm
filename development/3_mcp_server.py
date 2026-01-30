from mcp.server.fastmcp import FastMCP
mcp = FastMCP("WhatsAppCRM")

@mcp.tool()
def search_whatsapp_contact(name: str) -> str:
    """Search for a customer in the WhatsApp CRM database."""
    # Mock database logic
    contacts = {
        "alice": "Alice Johnson (ID: wa_9988) - Status: Active Lead",
        "bob": "Bob Smith (ID: wa_7766) - Status: Existing Customer"
    }
    return contacts.get(name.lower(), f"No contact found for '{name}'")

if __name__ == "__main__":
    mcp.run()