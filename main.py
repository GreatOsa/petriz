"""Main executable"""

import fastapi
import asyncio
import uvloop

from helpers.fastapi import commands
from core import application


asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
app: fastapi.FastAPI = application.main()


if __name__ == "__main__":
    commands.management()
