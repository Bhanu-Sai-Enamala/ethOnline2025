from uagents import Agent, Context, Model
from uagents.setup import fund_agent_if_low
import asyncio

class Message(Model):
    message: str

class Response(Model):
    text: str

# Create the sender agent
sender_agent = Agent(
    name="message_sender",
    port=8001,
    seed="message_sender_seed_phrase_change_this",
    endpoint=["http://127.0.0.1:8001/submit"],
    mailbox=True  # Makes the agent's address stable (optional
)

# Fund agent if balance is low (for testnet)
fund_agent_if_low(sender_agent.wallet.address())

# Replace this with your responder agent's address from Agentverse
RESPONDER_AGENT_ADDRESS = "agent1q0ae09q6wxp9vwgtj03zdrsnnc4at5xned3xnyq85mxgna4hc2ec6amm0uf" # Get this from your deployed responder agent

print(f"Sender agent address: {sender_agent.address}")
print(f"Sender agent name: {sender_agent.name}")

@sender_agent.on_event("startup")
async def send_message(ctx: Context):
    """Send a message to the responder agent on startup"""
    ctx.logger.info("Sender agent started!")
    
    # Wait a moment for startup
    await asyncio.sleep(2)
    
    # Create and send message
    message = Message(message="Hi there! Please respond with hello world.")
    
    ctx.logger.info(f"Sending message to responder agent: {RESPONDER_AGENT_ADDRESS}")
    await ctx.send(RESPONDER_AGENT_ADDRESS, message)
    ctx.logger.info("Message sent!")

@sender_agent.on_message(model=Response)
async def handle_response(ctx: Context, sender: str, msg: Response):
    """Handle responses from the responder agent"""
    ctx.logger.info(f"Received response from {sender}: {msg.text}")
    print(f"ðŸŽ‰ Got response: {msg.text}")

@sender_agent.on_interval(period=30.0)
async def send_periodic_message(ctx: Context):
    """Send a message every 30 seconds"""
    message = Message(message="Periodic ping - please respond!")
    ctx.logger.info("Sending periodic message...")
    await ctx.send(RESPONDER_AGENT_ADDRESS, message)

if __name__ == "__main__":
    print("Starting Message Sender Agent...")
    print(f"Will send messages to: {RESPONDER_AGENT_ADDRESS}")
    print("Make sure to update RESPONDER_AGENT_ADDRESS with your deployed agent's address!")
    sender_agent.run()
