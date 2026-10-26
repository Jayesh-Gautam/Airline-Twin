"""Great-circle helpers (spherical earth, km and degrees)."""
import math

R_KM = 6371.0


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_KM * math.asin(math.sqrt(min(1.0, a)))


def bearing(lat1, lon1, lat2, lon2):
    """Initial heading from point 1 to point 2, degrees clockwise from north."""
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def interpolate(lat1, lon1, lat2, lon2, f):
    """Point a fraction f (0..1) of the way along the great circle."""
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d = distance_km(lat1, lon1, lat2, lon2) / R_KM
    if d < 1e-9:
        return lat1, lon1
    a, b = math.sin((1 - f) * d) / math.sin(d), math.sin(f * d) / math.sin(d)
    x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
    y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
    z = a * math.sin(p1) + b * math.sin(p2)
    return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))


def arc(lat1, lon1, lat2, lon2, n=48):
    """Points along the great circle, longitudes unwrapped so lines don't jump at +-180."""
    pts, prev = [], None
    for i in range(n + 1):
        la, lo = interpolate(lat1, lon1, lat2, lon2, i / n)
        if prev is not None:
            while lo - prev > 180:
                lo -= 360
            while lo - prev < -180:
                lo += 360
        pts.append([round(la, 4), round(lo, 4)])
        prev = lo
    return pts


def position(lat1, lon1, lat2, lon2, f):
    """(lat, lon, heading) of an aircraft a fraction f along its route."""
    f = max(0.0, min(1.0, f))
    la, lo = interpolate(lat1, lon1, lat2, lon2, f)
    ahead = interpolate(lat1, lon1, lat2, lon2, min(1.0, f + 0.01))
    hd = bearing(la, lo, *ahead) if f < 0.995 else bearing(lat1, lon1, lat2, lon2)
    return la, lo, hd
