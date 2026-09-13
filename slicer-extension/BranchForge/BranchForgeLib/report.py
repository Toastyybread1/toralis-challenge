"""Readable presentation of the unmodified challenge contract (no medical claims)."""
from html import escape
import math


def prediction_html(data, synthetic=False):
    if data is None:
        return "<h3>Results, in plain language</h3><p>Load a study and run detection, or import its JSON.</p>"
    branches = data["daughters"]
    heading = "Synthetic reference geometry" if synthetic else "Detected branch candidates"
    parts = [f"<h3>{heading}</h3><p>Study: <b>{escape(data['case_id'])}</b><br>"
             f"{len(branches)} direct branches linked to the parent aorta.</p>",
             "<p>Origin = opening in the aorta. Seed = point inside the daughter vessel. "
             "Radius = estimated distance from the centre to the vessel wall.</p>",
             "<p>Coordinates are physical <b>LPS millimetres</b>: +X left, +Y posterior (back), "
             "+Z superior (head). Direction is a unit vector, not a distance.</p>"]
    if not branches:
        parts.append("<p><b>No branches were returned.</b> This does not prove there are no branches; review the CT for missed openings.</p>")
    for branch in branches:
        xyz = lambda key: ", ".join(f"{v:.2f}" for v in branch[key])
        chord = math.dist(branch["ostium_xyz_mm"], branch["seed_xyz_mm"])
        parts.append(f"<hr><h3>{escape(branch['instance_id'])}</h3>"
                     f"<p>Estimated radius: <b>{branch['radius_mm']:.2f} mm</b> "
                     f"(diameter: {2 * branch['radius_mm']:.2f} mm)<br>"
                     f"Origin (X, Y, Z): {xyz('ostium_xyz_mm')} mm<br>"
                     f"Seed (X, Y, Z): {xyz('seed_xyz_mm')} mm<br>"
                     f"Direction (X, Y, Z): {xyz('direction_xyz')}<br>"
                     f"Straight-line origin to seed: {chord:.2f} mm</p>")
    parts.append("<hr><p>The target seed is 5 mm along the vessel path; its straight-line distance can be shorter. "
                 "Arrows illustrate direction and rings illustrate radius estimates—not complete daughter-vessel walls. "
                 "Research prototype; not a diagnosis or a clinically validated measurement.</p>")
    return "".join(parts)
