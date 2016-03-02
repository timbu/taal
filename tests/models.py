from __future__ import absolute_import

from sqlalchemy import (
    Column, Integer as SaInteger, String as SaString, Text, ForeignKey)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

from taal.models import TranslationMixin
from taal import sqlalchemy as taal_sqlalchemy
from taal.sqlalchemy import types as taal_sqlalchemy_types


Base = declarative_base()


class Translation(TranslationMixin, Base):
    __tablename__ = "translations"


class Parent(Base):
    __tablename__ = "test_parent"

    id = Column(SaInteger, primary_key=True)
    name = Column(taal_sqlalchemy.TranslatableString(20))
    identifier = Column(SaString(20))


class Child(Base):
    __tablename__ = "test_child"

    id = Column(SaInteger, primary_key=True)
    name = Column(taal_sqlalchemy.TranslatableString(20))
    identifier = Column(SaString(20))
    parent_id = Column(SaInteger, ForeignKey('test_parent.id'))
    parent = relationship('Parent', backref='children')


class Model(Base):
    __tablename__ = "models"

    id = Column(SaInteger, primary_key=True)
    name = Column(taal_sqlalchemy.TranslatableString)
    identifier = Column(Text)


class RequiredModel(Base):
    __tablename__ = "requiredmodels"

    id = Column(SaInteger, primary_key=True)
    name = Column(taal_sqlalchemy.TranslatableString, nullable=False)
    identifier = Column(Text)


class RenamedColumn(Base):
    __tablename__ = "renamedcolumns"

    id = Column(SaInteger, primary_key=True)
    name = Column('other', taal_sqlalchemy.TranslatableString, nullable=False)
    one = Column('two', SaInteger)


# Consider moving to the TranslationContextManager
def _create_translation(
        session, language, context, message_id, translation_str):
    translation = Translation(
        context=context,
        message_id=message_id,
        language=language,
        value=translation_str)
    session.add(translation)
    session.commit()


def create_translation_for_model(
        session, language, obj, field, translation_str):
    context = taal_sqlalchemy_types.get_context(obj, field)
    message_id = taal_sqlalchemy_types.get_message_id(obj)
    return _create_translation(
        session, language, context, message_id, translation_str)
