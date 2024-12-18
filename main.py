"""Main executable"""

import fastapi

from helpers.fastapi import commands
from core import application
from core.commands import COMMANDS_REGISTRY


app: fastapi.FastAPI = application.main()


if __name__ == "__main__":
    commands.main(commands_registry=COMMANDS_REGISTRY)
