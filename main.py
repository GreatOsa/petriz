"""Main executable"""

import fastapi

from helpers.fastapi import commands
from core import application


app: fastapi.FastAPI = application.main()


if __name__ == "__main__":
    commands.management()
