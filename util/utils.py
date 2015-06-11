import pg8000
import math
import coord_utils
from ..geo_util import coord_sys as cs


def create_tile_geo(lon, lat):
    easting, northing = coord_utils.db_get_easting_northing(lon, lat)

    # point to mercator, find nearest grid tile lower left

    e_ll = math.floor(easting / 1000.0 * 2.0) / 2.0 * 1000.0
    n_ll = math.floor(northing / 1000.0 * 2.0) / 2.0 * 1000.0

    dist_m = 500
    geo = [(e_ll, n_ll), (e_ll, n_ll + dist_m), (e_ll + dist_m, n_ll + dist_m),
              (e_ll + dist_m, n_ll), (e_ll, n_ll)]
    geo_string = 'POLYGON((' + ','.join([' '.join([str(a) for a in x]) for x in geo]) + '))'
    return 'SRID=%d;%s' % (cs.WEB_MERCATOR_CODE, geo_string)

def get_country_for_polygon(geo_string):
    transform = coord_utils.wgs84_string_coord_to_mercator(geo_string)
    select = "SELECT ogc_fid FROM country_bounds where ST_Contains(wkb_geometry, ST_Centroid(%s))" % transform
    conn = pg8000.connect()
    curs = conn.cursor()
    curs.execute(select)
    result = curs.fetchone()
    if result and len(result) == 1:
        return result[0]

    curs = conn.cursor()
    intersect = "SELECT ogc_fid FROM country_bounds where ST_Intersects(wkb_geometry, %s)" % transform
    curs.execute(intersect)
    result = curs.fetchone()
    if result:
      return result[0]

    curs = conn.cursor()
    nearby = "SELECT ogc_fid FROM country_bounds ORDER BY wkb_geometry <-> ST_Centroid(%s) LIMIT 1" % transform
    curs.execute(nearby)
    result = curs.fetchone()
    return result[0]

# for debug
_tile_was_created = False

def get_or_create_tile(coord):
    #print 'coord', coord
    conn = pg8000.connect()
    curs = conn.cursor()
    pk = None
    try:
        point = coord_utils.wgs84_coord_to_mercator(coord[0], coord[1])
        curs.execute("SELECT tile_pk FROM tile where "
                     "ST_Contains(wkb_geometry, %s)" % point)
        pk = curs.fetchone()[0]
    except pg8000.Error:
        pass

    global _tile_was_created
    if pk:
        _tile_was_created = False
        return pk

    lat = coord[1]
    lon = coord[0]
    if not isinstance(lat, float) or not isinstance(lon, float):
        print "bad lat lon: ", lat, lon
        return None

    geo = create_tile_geo(lon, lat)
    geo_string = 'POLYGON((' + ','.join([' '.join([str(a) for a in x]) for x in geo]) + '))'

    try:
        country_pk = get_country(geo_string)
    except pg8000.Error:
        print "no country: " + geo_string
        get_country_for_polygon( geo_string)
        return None

    conn = pg8000.connect()
    curs = conn.cursor()
    q = "insert into tile(wkb_geometry, country_fk) values(ST_GeomFromText('%s', %d), %d) returning tile_pk" \
        % (geo_string, coord_utils.mercator_id, country_pk)
    #print q
    curs.execute(q)
    conn.commit()
    _tile_was_created = True
    pk = curs.fetchone()[0]
    #print geo_string
    return pk

def get_user_pk(username):
    conn = pg8000.connect()
    curs = conn.cursor()
    pk = None
    try:
        curs.execute("select userinfo_pk from userinfo where name='%s'" % username)
        pk = curs.fetchone()[0]
    except pg8000.Error:
        pass
    return pk