"""
Ports up a river that the sea network does not follow: the river leg of their routes.

The sea network (searoute) ends on the coast. A port far up an estuary has no node near it, and the router used to snap
it to the nearest node, which can be on another stretch of coast (Rouen, 53 km from the network, went to a node near
Dieppe: barley from France to the Netherlands read 196 nm, less than Le Havre to Rotterdam, 246 nm). A port in RIVER_LEGS
is routed from `mouth`, a node of the network, and the leg is added to the distance of every route and every alternative
that starts or ends at the port (routing.route()). The drawn line runs from the port's own point to the mouth in one straight
segment, and the lane and route pages say so. The pages' notes are written here from the table, so that a note never says more
than the table does.

Each row: the port code, the river, the mouth (name and the coordinates of a node of the network: a test checks that it is one),
the length of the leg in km as the page gives it, and the page with the sentence that gives it. The leg in nautical miles is
the length divided by the nautical mile (pipeline/common/constants.py), rounded.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common import constants as CN  # noqa: E402  (the nautical mile, with the page that gives it)

RIVER_LEGS = {
    # Port de Rouen (French Wikipedia, CC BY-SA 4.0, read 24 November 2026), section on the port's activity: "L'activité portuaire se
    # répartit tout au long de la Seine entre Rouen et Honfleur sur environ 120 km." (the port's activity is spread along the Seine
    # between Rouen and Honfleur over about 120 km). The mouth is the node of the network nearest to Honfleur (3.5 km), in the estuary:
    # the network's own path from it to the open sea passes Le Havre (8 to 10 nm), so a route from Rouen is the 65 nm of the river
    # plus the estuary plus the sea route of Le Havre, which is what a ship sails.
    "FRURO": {
        "river": "Seine",
        "mouth_name": "Honfleur",
        "mouth": [0.267638, 49.434681],
        "km": 120,
        "s": "wikipedia",
        "url": "https://fr.wikipedia.org/wiki/Port_de_Rouen",
        "page": "Port de Rouen, French Wikipedia",
        "sentence": "L'activité portuaire se répartit tout au long de la Seine entre Rouen et Honfleur sur environ 120 km.",
    },
}


def nm_of(leg):
    """Length of a river leg in nautical miles, whole."""
    return round(leg["km"] / CN.KM_PER_NAUTICAL_MILE)


def note(leg, port_name):
    """The sentence of the lane, route and finder pages: what the distance includes and how the leg is drawn."""
    return (f"{port_name} is up the {leg['river']}, off the sea network: the distance includes about {nm_of(leg)} nm of the {leg['river']} "
            f"between {leg['mouth_name']} and the port ({leg['km']} km, {leg['page']}), and the line is drawn from the port to "
            f"{leg['mouth_name']} as one straight segment, not along the river.")


def public(code, port_name):
    """What the lane and pairs files publish for a port with a leg: {river, mouth, km, nm, s, url, n}, or None."""
    leg = RIVER_LEGS.get(code)
    if not leg:
        return None
    return {"river": leg["river"], "mouth": leg["mouth_name"], "km": leg["km"], "nm": nm_of(leg), "s": leg["s"], "url": leg["url"],
            "n": note(leg, port_name)}


_points = {}


def by_point():
    """{(lon, lat) of the port rounded to 4 decimals: leg + its code}: the router works on points, not on codes."""
    if not _points:
        import ports as P  # noqa: E402  (ports does not import the router)
        for code, leg in RIVER_LEGS.items():
            x, y = P.port(code)["at"]
            _points[(round(x, 4), round(y, 4))] = {**leg, "code": code, "nm": nm_of(leg)}
    return _points


def leg_at(pt):
    """The leg of the port at [lon, lat], or None."""
    return by_point().get((round(pt[0], 4), round(pt[1], 4)))
