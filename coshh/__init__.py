"""
COSHH form generation: hazard data in, a filled teaching-lab form out.

`coshh.rules` is the reasoning layer — it turns GHS hazard codes into the ticks
this particular form asks for. It holds no network code and no Word code, so it
can be read and argued with on its own, which is the point: a form somebody
signs should be defensible line by line.
"""

__all__ = ["rules"]
