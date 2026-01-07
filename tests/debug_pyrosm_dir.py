import pyrosm
from pyrosm import OSM

# print("Pyrosm version:", pyrosm.__version__)
print("Attributes in pyrosm:", dir(pyrosm))

try:
    from pyrosm.graphs import to_graph
    print("Found to_graph in pyrosm.graphs")
except ImportError:
    print("Not found in pyrosm.graphs")

print("Attributes in OSM class:", dir(OSM))
