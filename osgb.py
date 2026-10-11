#!/usr/bin/env python3
"""British National Grid eastings and northings to WGS84 latitude and longitude.

Natural Resources Wales publish their gauge positions as OSGB36 grid references
and nothing else — no latitude, no longitude — so without this there is no way
to put a Welsh gauge on a map, work out which county it is in, or find the
nearest bathing water to it.

Two steps, and skipping the second is the usual mistake: the grid is a
projection of the OSGB36 datum, so converting the projection alone leaves a
position on OSGB36, which sits about 70 to 120 metres from the same point on
WGS84 across Britain. That is enough to put a gauge in the wrong parish and, on
this site, to pick the wrong county for a breadcrumb. The Helmert transform
below is the Ordnance Survey's own published approximation, good to a few
metres, which is far finer than anything here needs.

No dependencies on purpose: the collector runs on a bare runner and this is
thirty lines of arithmetic.
"""

import math

# Airy 1830, the OSGB36 ellipsoid, and the National Grid projection constants.
A, B = 6377563.396, 6356256.909
F0 = 0.9996012717
LAT0, LON0 = math.radians(49.0), math.radians(-2.0)
E0, N0 = 400000.0, -100000.0
E2 = 1 - (B * B) / (A * A)
N = (A - B) / (A + B)

# WGS84.
A_WGS, B_WGS = 6378137.000, 6356752.3141
E2_WGS = 1 - (B_WGS * B_WGS) / (A_WGS * A_WGS)

# OSGB36 -> WGS84, the Ordnance Survey's published seven-parameter approximation.
TX, TY, TZ = 446.448, -125.157, 542.060
RX = math.radians(0.1502 / 3600.0)
RY = math.radians(0.2470 / 3600.0)
RZ = math.radians(0.8421 / 3600.0)
S = -20.4894e-6


def _grid_to_osgb36(east, north):
    """Grid eastings and northings to OSGB36 latitude and longitude, in radians."""
    lat = LAT0
    m = 0.0
    for _ in range(12):
        lat = (north - N0 - m) / (A * F0) + lat
        n1 = (1 + N + 1.25 * N ** 2 + 1.25 * N ** 3) * (lat - LAT0)
        n2 = (3 * N + 3 * N ** 2 + 2.625 * N ** 3) * math.sin(lat - LAT0) * math.cos(lat + LAT0)
        n3 = (1.875 * N ** 2 + 1.875 * N ** 3) * math.sin(2 * (lat - LAT0)) * math.cos(2 * (lat + LAT0))
        n4 = (35.0 / 24.0) * N ** 3 * math.sin(3 * (lat - LAT0)) * math.cos(3 * (lat + LAT0))
        m = B * F0 * (n1 - n2 + n3 - n4)
        if abs(north - N0 - m) < 1e-5:
            break
    s = math.sin(lat)
    nu = A * F0 / math.sqrt(1 - E2 * s * s)
    rho = A * F0 * (1 - E2) / (1 - E2 * s * s) ** 1.5
    eta2 = nu / rho - 1
    t = math.tan(lat)
    sec = 1.0 / math.cos(lat)
    vii = t / (2 * rho * nu)
    viii = t / (24 * rho * nu ** 3) * (5 + 3 * t ** 2 + eta2 - 9 * t ** 2 * eta2)
    ix = t / (720 * rho * nu ** 5) * (61 + 90 * t ** 2 + 45 * t ** 4)
    x = sec / nu
    xi = sec / (6 * nu ** 3) * (nu / rho + 2 * t ** 2)
    xii = sec / (120 * nu ** 5) * (5 + 28 * t ** 2 + 24 * t ** 4)
    xiia = sec / (5040 * nu ** 7) * (61 + 662 * t ** 2 + 1320 * t ** 4 + 720 * t ** 6)
    de = east - E0
    out_lat = lat - vii * de ** 2 + viii * de ** 4 - ix * de ** 6
    out_lon = LON0 + x * de - xi * de ** 3 + xii * de ** 5 - xiia * de ** 7
    return out_lat, out_lon


def _helmert(lat, lon):
    """OSGB36 radians to WGS84 radians, via geocentric cartesian coordinates."""
    s = math.sin(lat)
    nu = A / math.sqrt(1 - E2 * s * s)
    x = nu * math.cos(lat) * math.cos(lon)
    y = nu * math.cos(lat) * math.sin(lon)
    z = (1 - E2) * nu * s
    x2 = TX + x * (1 + S) - y * RZ + z * RY
    y2 = TY + x * RZ + y * (1 + S) - z * RX
    z2 = TZ - x * RY + y * RX + z * (1 + S)
    lon2 = math.atan2(y2, x2)
    p = math.sqrt(x2 * x2 + y2 * y2)
    lat2 = math.atan2(z2, p * (1 - E2_WGS))
    for _ in range(12):
        nu2 = A_WGS / math.sqrt(1 - E2_WGS * math.sin(lat2) ** 2)
        new = math.atan2(z2 + E2_WGS * nu2 * math.sin(lat2), p)
        if abs(new - lat2) < 1e-12:
            lat2 = new
            break
        lat2 = new
    return lat2, lon2


def to_wgs84(east, north):
    """(easting, northing) -> (lat, lon) in degrees, WGS84."""
    lat, lon = _grid_to_osgb36(float(east), float(north))
    lat, lon = _helmert(lat, lon)
    return math.degrees(lat), math.degrees(lon)


if __name__ == "__main__":
    # Ordnance Survey's own worked example, plus places whose position is easy
    # to check against a map. OS give Caister Water Tower as TG 51409 13177 at
    # 52.6575N 1.7179E on OSGB36; on WGS84 that is about 52.65757N 1.71660E.
    for name, e, n, want in (
        ("OS worked example (Caister)", 651409.903, 313177.270, (52.6576, 1.7166)),
        ("Aberaeron gauge", 245963, 262365, (52.2428, -4.2593)),
        ("Cardiff centre", 318000, 176500, (51.4800, -3.1800)),
    ):
        lat, lon = to_wgs84(e, n)
        d = ((lat - want[0]) ** 2 + (lon - want[1]) ** 2) ** 0.5 * 111.0
        print("%-30s %.5f, %.5f   %.2f km from expected" % (name, lat, lon, d))
