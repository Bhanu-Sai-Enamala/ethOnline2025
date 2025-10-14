# local_client_agent.py
from uagents import Agent, Context
from agents.peg_models import PegCheckRequest, PegCheckResponse

# Fill this with your Responder's Agentverse address (NOT URL)
RESPONDER_AGENT_ADDRESS = "agent1qf5yrm5c86hv5h33stxpffe7mpplxjpxqxevxkss27phmaws2d49jy2veck"  # e.g. agent1qxxxxx...

agent = Agent(
    name="local-client",
    seed="local client fixed seed",
    mailbox=True   # makes your address stable (optional)
)

@agent.on_event("startup")
async def ask_snapshot(ctx: Context):
    ctx.logger.info("Requesting latest peg snapshot from responder…")
    await ctx.send(RESPONDER_AGENT_ADDRESS, PegCheckRequest())

@agent.on_message(model=PegCheckResponse)
async def handle_snapshot(ctx: Context, sender: str, msg: PegCheckResponse):
    ctx.logger.info(f"Got PegCheckResponse (ok={msg.ok}) from {sender}")
    ctx.logger.info(msg.payload_json)

if __name__ == "__main__":
    agent.run()