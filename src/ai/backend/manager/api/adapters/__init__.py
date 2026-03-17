"""Shared adapters used by both REST handlers and GQL resolvers.

Each adapter wraps a Processor and exposes DTO-in, DTO-out methods,
eliminating direct Processor calls from GQL resolvers and REST handlers.
"""
