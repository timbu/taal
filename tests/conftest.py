from __future__ import absolute_import

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker


def pytest_addoption(parser):
    parser.addoption(
        "--neo4j_uri", action="store",
        default="temp://",
        help=(
            "URI for establishing a connection to neo4j. See the docs for"
            " valid URIs"))

    parser.addoption(
        "--db_uri", action="store",
        help="Sqlalchemy connection string"
    )


def pytest_collection_modifyitems(items):
    """ mark items by requirements for (de-)selecting """
    for item in items:
        if item.__class__.__name__ == "DoctestTextfile":
            # test_requirements.txt collected erroneously
            continue

        if 'session_cls' in item.fixturenames:
            item.keywords["sql"] = pytest.mark.sql
        if 'manager' in item.fixturenames:
            item.keywords["neo4j"] = pytest.mark.neo4j


@pytest.fixture(scope="session")
def clean_engine(request):
    # importing at the module level messes up coverage
    from tests.models import Base

    connection_string = request.config.getoption('db_uri')
    if connection_string is None:
        raise RuntimeError("No database connection string specified")

    def drop_and_recreate_db():
        connection_url = make_url(connection_string)
        database = connection_url.database
        connection_url.database = None  # may not exist, so don't connect to it
        engine = create_engine(connection_url)
        query = 'DROP DATABASE IF EXISTS {0}; CREATE DATABASE {0}'.format(
            database)
        engine.execute(query)

    engine = create_engine(connection_string)
    drop_and_recreate_db()
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session_cls(request, clean_engine):
    from tests.models import Base
    engine = clean_engine
    session_cls = sessionmaker(bind=engine)
    connection = engine.connect()
    transaction = connection.begin()
    for table in reversed(Base.metadata.sorted_tables):
        connection.execute(table.delete())
    transaction.commit()

    request.addfinalizer(session_cls.close_all)
    return session_cls


@pytest.fixture
def session(request, session_cls):
    return session_cls()


@pytest.fixture
def bound_session(request, session, session_cls):
    # importing at the module level messes up coverage
    from taal import Translator
    from tests.models import Translation

    translator = Translator(Translation, session_cls(), 'language')
    translator.bind(session)
    return session
