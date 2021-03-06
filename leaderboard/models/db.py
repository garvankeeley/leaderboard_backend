import datetime
from sqlalchemy import Column, Integer, CheckConstraint
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import scoped_session
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.orm.exc import NoResultFound
from leaderboard.db import engine, Base
from os.path import expanduser, join, exists

import json

from leaderboard.db import session_factory


class LeaderboardGlobals(Base):
    """ Store global infdo here such as the current_week for the weekly rollover """
    __tablename__ = 'leadsserboard_globals'
    current_week = Column(Integer)
    id = Column(Integer, primary_key=True)
    CheckConstraint("0 < current_week and current_week < 54")

    @staticmethod
    def get_globals():
        session = session_factory()
        with session.begin(subtransactions=True):
            try:
                return session.query(LeaderboardGlobals).one()
            except NoResultFound:
                lg = LeaderboardGlobals()
                session.add(lg)
                return lg

    @staticmethod
    def get_current_week():
        g = LeaderboardGlobals.get_globals()
        if not g.current_week or not 0 < g.current_week < 54:
            session = session_factory()
            with session.begin(subtransactions=True):
                g.current_week = datetime.date.today().year
                session.add(g)

        return g.current_week

    @staticmethod
    def is_week_rolling_over():
        """ Weeks 1-53 are stored in the db, and are reused as the year rolls over.
        As week 1 turns into week2 (for example), week2 must be truncated before using it.
        The current week is stored in the LeaderboardGlobals.
        This function both checks for rollover, and updates the db to the new week.

        :return: True if the actual week is greater than the current week in the db
        """

        from leaderboard.models import reportweeks

        week_in_db = LeaderboardGlobals.get_current_week()
        actual_week = reportweeks.current_week_number()
        is_rollover = actual_week != week_in_db
        if is_rollover:
            session = session_factory()
            with session.begin(subtransactions=True):
                  lbGlobals = LeaderboardGlobals.get_globals()
                  lbGlobals.current_week = actual_week
                  session.add(lbGlobals)
        return is_rollover


class DB(object):
    instance = None

    def __init__(self):
        jdata = self.load_home_config()
        if not jdata:
            jdata = self.load_etc_config()

        if not jdata:
            raise RuntimeError("Can't load JSON configuration")

        self.engine = engine

        self.session_factory = scoped_session(sessionmaker(bind=self.engine,
                                                           expire_on_commit=False,
                                                           autocommit=True))
        LeaderboardGlobals.__table__.create(bind=engine, checkfirst=True)

    def _load_config(self, fpath):
        try:
            db_json = open(fpath)
            if exists(fpath):
                return json.load(db_json)
        except:
            return None

    def load_etc_config(self):
        """
        Return the JSON blob from the /etc directory, or None if the
        file can't be loaded.
        """
        fpath = '/etc/mozilla/stumbler_leaderboard/db.json'
        return self._load_config(fpath)

    def load_home_config(self):
        """
        Return the JSON blob from the home directory, or None if the
        file can't be loaded.
        """
        fpath = join(expanduser("~"), ".stumbler_leaderboard", 'db.json')
        return self._load_config(fpath)

    def table_exists(self, name):
        inspector = Inspector.from_engine(get_db().engine)
        return name in inspector.get_table_names()

    def get_metadata(self):
        return Base.metadata

    def create_all(self):
        from leaderboard.models.country_bounds import CountryBounds  # NOQA
        from leaderboard.models.contributor import Contributor  # NOQA
        from leaderboard.models.tile import Tile  # NOQA

        do_load = not self.table_exists(CountryBounds.__tablename__)
        self.get_metadata().create_all(self.engine)

        if do_load:
            CountryBounds.load_countries()

    def drop_all(self):
        from leaderboard.models.country_bounds import CountryBounds  # NOQA
        from leaderboard.models.contributor import Contributor  # NOQA
        from leaderboard.models.tile import Tile  # NOQA
        from leaderboard.models.reportweeks import get_current_reportweek_class

        wk = get_current_reportweek_class()
        if self.table_exists(wk.__tablename__):
            t = wk.__table__
            t.drop(get_db().engine)
        for tbl in reversed(get_db().get_metadata().sorted_tables):
            if self.table_exists(tbl.name):
                get_db().engine.execute(tbl.delete())
                tbl.drop(get_db().engine)

        session = session_factory()
        with session.begin(subtransactions=True):
            session.expunge_all()
            session.expire_all()


def get_db():
    """
    :rtype: DB
    """
    if not DB.instance:
        DB.instance = DB()
    return DB.instance
