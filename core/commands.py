from helpers.fastapi import commands


COMMANDS_REGISTRY = {}

register = commands.make_registrar(COMMANDS_REGISTRY)
"""
Decorator to register a command handler with the project-wide command registry
"""


__all__ = ["COMMANDS_REGISTRY", "register"]
