"""
handlers.__init__
Registers command and message handlers to the bot instance.
This file exposes register_handlers(bot) to keep main.py tidy.
"""
from . import commands, messages

def register_handlers(bot):
    """
    Register all handler groups.
    Keep the order predictable: commands first, then messages.
    """
    commands.register(bot)
    messages.register(bot)
