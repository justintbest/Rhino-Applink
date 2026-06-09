"""
Push a polyline to the bowl backend as an A-Line.
Logs in fresh on each click using the email + password inputs.
"""

import json
import Rhino
import Rhino.Geometry as rg
import System
from urllib import request, error


# ── Coerce whatever the input parameter delivers into a Rhino Curve ─────────
def coerce_curve(obj):
    """Accepts Curve, Polyline, GUID, or RhinoObject. Returns a Curve or None."""
    if obj is None:
        return None

    # Already a Curve
    if isinstance(obj, rg.Curve):
        return obj

    # A bare Polyline → wrap as PolylineCurve
    if isinstance(obj, rg.Polyline):
        return rg.PolylineCurve(obj)

    # A doc-object GUID → look up the underlying geometry
    if isinstance(obj, System.Guid):
        doc_obj = Rhino.RhinoDoc.ActiveDoc.Objects.Find(obj)
        if doc_obj is None:
            return None
        geo = doc_obj.Geometry
        if isinstance(geo, rg.Curve):
            return geo
        if isinstance(geo, rg.Polyline):
            return rg.PolylineCurve(geo)
        return None

    # A RhinoObject directly
    if hasattr(obj, "Geometry"):
        geo = obj.Geometry
        if isinstance(geo, rg.Curve):
            return geo

    return None


# ── HTTP helper ──────────────────────────────────────────────────────────────
def post_json(url, data, token=None):
    body = json.dumps(data).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError("HTTP {0}: {1}".format(e.code, text))
    except error.URLError as e:
        raise RuntimeError("network error: {0}".format(e.reason))


# ── Main ─────────────────────────────────────────────────────────────────────
def push():
    if not run:
        return "set 'run' to True to POST"

    if not email or not password:
        return "email and password are required"
    if not name or not name.strip():
        return "name is required"

    curve = coerce_curve(polyline)
    if curve is None:
        return "polyline input is empty or not a curve"

    base = (baseUrl or "https://bowl-backend-x0jz.onrender.com").rstrip("/")
    is_closed = True if closed is None else bool(closed)

    # Extract polyline corners
    ok, poly = curve.TryGetPolyline()
    if not ok:
        return "input is not a polyline — convert via _Convert or use a Polyline"

    pts = [(p.X, p.Y) for p in poly]

    # Drop duplicate closing vertex if present
    if is_closed and len(pts) >= 2:
        dx = abs(pts[0][0] - pts[-1][0])
        dy = abs(pts[0][1] - pts[-1][1])
        if dx < 1e-6 and dy < 1e-6:
            pts = pts[:-1]

    if len(pts) < 3:
        return "need at least 3 distinct points (got {0})".format(len(pts))

    # Log in
    try:
        login_resp = post_json(
            base + "/api/v1/auth/login",
            {"email": email.strip(), "password": password},
        )
    except RuntimeError as e:
        return "login failed: {0}".format(e)

    token = login_resp.get("token")
    if not token:
        return "login returned no token"

    # Create A-Line
    body = {
        "name":   name.strip(),
        "closed": is_closed,
        "points": [{"x": x, "y": y} for x, y in pts],
    }
    try:
        aline = post_json(base + "/api/v1/alines", body, token=token)
    except RuntimeError as e:
        return "create failed: {0}".format(e)

    return "A-Line created  id={0}  name={1}  points={2}".format(
        aline.get("id"), aline.get("name"), len(pts)
    )


result = push()
print("DEBUG result =", result)
