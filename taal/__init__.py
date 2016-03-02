""" Taal: Translations for SQLAlchemy and Kaiso models

    Store and manage translations using SQLAlchemy
"""

from __future__ import absolute_import

from abc import ABCMeta, abstractmethod, abstractproperty

from sqlalchemy import func
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.expression import and_, or_, desc

from taal.constants import TRANSPARENT_VALUES
from taal.exceptions import BindError


try:
    VERSION = __import__('pkg_resources').get_distribution('taal').version
except:  # pragma: no cover
    VERSION = 'unknown'


NULL = None  # for pep8


class TranslationMissing(object):
    def __repr__(self):
        return "<TranslationMissing sentinel>"


TRANSLATION_MISSING = TranslationMissing()


def is_translatable_value(value):
    return value not in TRANSPARENT_VALUES


class TranslatableString(object):
    """
    Placeholder for a string to be translated

    Holds metadata, ``context`` and ``message_id``, and optionally
    a string ``pending_value``
    """

    def __init__(self, context=None, message_id=None, pending_value=None):
        self.context = context
        self.message_id = message_id
        self.pending_value = pending_value

    def __repr__(self):
        return "<TranslatableString: ({}, {}, {})>".format(
            self.context, self.message_id, self.pending_value)

    def __eq__(self, other):
        if not isinstance(other, TranslatableString):
            return False

        self_data = (self.context, self.message_id, self.pending_value)
        other_data = (other.context, other.message_id, other.pending_value)
        return self_data == other_data

    def __hash__(self):
        return hash((self.context, self.message_id, self.pending_value))


class TranslationStrategies(object):
    NONE_VALUE = 'NONE_VALUE'
    SENTINEL_VALUE = 'SENTINEL_VALUE'
    DEBUG_VALUE = 'DEBUG_VALUE'

    _valid_strategies = (
        NONE_VALUE,
        SENTINEL_VALUE,
        DEBUG_VALUE,
    )

    @classmethod
    def validate(cls, strategy):
        if strategy not in cls._valid_strategies:
            raise ValueError(u"Invalid strategy `{}`".format(strategy))


class Translator(object):
    """
    Manage a particular set of translations

    Given a sqlalchemy session, a model to store translations, and
    a language, bind a translator to a(n other) sqlalchemy session

    Language may be either a string, or a callable returning a string, for
    more dynamic behaviour.

    In addition to native data types, attributes will also include
    instances of ``TranslatableString``. A translator may subsequently
    be passed "structured" data (dicts, lists, tuples) containing
    translatable strings and translate to a particular language

    Strategy for missing translations
    ---------------------------------
    By default, if there is no translation available, `None` is returned. This
    behaviour may be changed by passing a `strategy`, either when constructing
    a :class:`Translator`, or to :meth:`Translator.translate`. Possible
    strategies are:

        :attr:`Translator.strategies.NONE_VALUE` : (default) Return `None`
        :attr:`Translator.strategies.SENTINEL_VALUE` : Return a sentinel
            value (:data:`taal.TRANSLATION_MISSING`)
        :attr:`Translator.strategies.DEBUG_VALUE` : Return a debug value (a
            string indicating a translating is missing, including context
            information)
    """
    strategies = TranslationStrategies

    def __init__(
        self, model, session, language, strategy=strategies.NONE_VALUE,
    ):
        self.model = model
        self.session = session

        self.strategies.validate(strategy)
        self.strategy = strategy

        if callable(language):
            self.get_language = language
        else:
            self.get_language = lambda: language

    @property
    def language(self):
        return self.get_language()

    def bind(self, target):

        if isinstance(target, Session):
            from taal.sqlalchemy.events import (
                register_translator, register_session)
            register_translator(target, self)
            register_session(target)
        else:
            raise BindError("Unknown target {}".format(target))

    def _get_debug_translation(self, translatable):
        return u"[Translation missing ({}, {}, {})]".format(
            self.language, translatable.context, translatable.message_id)

    def _translate(self, translatable, strategy, cache):
        if strategy is None:
            strategy = self.strategy

        try:
            return cache[(translatable.context, translatable.message_id)]
        except KeyError:
            if strategy == self.strategies.NONE_VALUE:
                return None
            if strategy == self.strategies.SENTINEL_VALUE:
                return TRANSLATION_MISSING
            if strategy == self.strategies.DEBUG_VALUE:
                return self._get_debug_translation(translatable)

    def translate(self, translatable, strategy=None, cache=None):
        """
        Translate ``TranslatableString`` by looking up a translation

        can also take a 'structure' (currently lists, tuples, and dicts)
        and recursively translate any TranslatableStrings found.
        """

        if strategy is not None:
            self.strategies.validate(strategy)

        if cache is None:
            cache = self._prepare_cache(translatable)

        if isinstance(translatable, TranslatableString):
            return self._translate(
                translatable, strategy=strategy, cache=cache)
        elif isinstance(translatable, dict):
            return dict(
                (key, self.translate(val, strategy=strategy, cache=cache))
                for key, val in translatable.items()
            )
        elif isinstance(translatable, list):
            return list(
                self.translate(item, strategy=strategy, cache=cache)
                for item in translatable)
        elif isinstance(translatable, tuple):
            return tuple(
                self.translate(item, strategy=strategy, cache=cache)
                for item in translatable)

        else:
            return translatable

    def _prepare_cache(self, translatable):
        """
        Bulk load translations required to translate a translatable
        'structure'
        """
        translatable_pks = self._collect_translatables(translatable)
        if not translatable_pks:
            return {}

        pk_filter = or_(*(
            and_(
                self.model.context == context,
                self.model.message_id == message_id
            )
            for context, message_id in translatable_pks
        ))

        translations = self.session.query(self.model).filter(
            self.model.language == self.language).filter(pk_filter).values(
            self.model.context, self.model.message_id, self.model.value)
        cache = {(t[0], t[1]): t[2] for t in translations}

        return cache

    def _collect_translatables(self, translatable, collection=None):
        """
        Run over a translatable 'structure' and collect the set of
        translatable primary keys (context and message_id tuples)
        These are then bulk loaded from the db
        """

        if collection is None:
            collection = set()

        if isinstance(translatable, TranslatableString):
            collection.add((translatable.context, translatable.message_id))
        elif isinstance(translatable, dict):
            [self._collect_translatables(val, collection)
                for val in translatable.values()]
        elif isinstance(translatable, list):
            [self._collect_translatables(item, collection)
                for item in translatable]
        elif isinstance(translatable, tuple):
            [self._collect_translatables(item, collection)
                for item in translatable]

        return collection

    def save_translation(self, translatable, commit=True):
        if translatable.message_id is None:
            raise RuntimeError(
                "Cannot save translatable '{}'. "
                "Message id is None".format(translatable))

        if translatable.pending_value is TRANSLATION_MISSING:
            raise RuntimeError(
                "Cannot save translatable '{}'. "
                "Pending value is `{!r}`".format(
                    translatable, TRANSLATION_MISSING))

        if self.strategy == self.strategies.DEBUG_VALUE:
            debug_value = self._get_debug_translation(translatable)
            if translatable.pending_value == debug_value:
                return

        translation = self.model(
            context=translatable.context,
            message_id=translatable.message_id,
            language=self.language
        )

        # we can use merge for 'on duplicate key update'
        # (only works in sqla if we're matching on the primary key)
        translation = self.session.merge(translation)
        translation.value = translatable.pending_value

        if commit:
            self.session.commit()

    def delete_translations(self, translatable, commit=True):
        """ delete _all_ translations for this (context, message_id) """
        self.session.query(self.model).filter_by(
            context=translatable.context,
            message_id=translatable.message_id,
        ).delete()

        if commit:
            self.session.commit()

    def move_translations(
            self, old_translatable, new_translatable, commit=True):
        self.session.query(self.model).filter_by(
            context=old_translatable.context,
            message_id=old_translatable.message_id,
        ).update({
            'context': new_translatable.context,
            'message_id': new_translatable.message_id,
        })

        if commit:
            self.session.commit()

    def _normalised_translations(self, languages, base_query=None):
        """ helper for bulk operations

        returns query, aliases, columns, where

        ``query`` is a sqlalchemy query that will select all contexts
        and message_ids from the translations table and join it to itself
        once for each language supplied in the languages list, returning
        rows of the form (
            context,
            message_id,
            translation in language 1,
            translation in language 2,
            ...
        )

        ``columns`` is a list of all columns in this tuple

        ``aliases`` are sqlalchemy aliases to the (self) joined language tables
        so that we can apply filters, e.g.
            query.filter(aliases[0].value == NULL)

        """
        session = self.session
        model = self.model

        if base_query is None:
            base_query = session.query(
                model.context, model.message_id).distinct()

        subquery = base_query.subquery(name='basequery')
        query = session.query(subquery)

        aliases = []
        for language in languages:
            alias = aliased(model, name=language)
            query = query.outerjoin(
                alias,
                and_(
                    alias.context == subquery.c.context,
                    alias.message_id == subquery.c.message_id,
                    alias.language == language
                )
            )
            aliases.append(alias)

        columns = [subquery.c.context, subquery.c.message_id] + [
            alias_.value for alias_ in aliases]

        return query, aliases, columns

    def list_translations(self, languages):
        """ list all translations for the requested languages

        return a tuple (context, message_id, value1, value2, ...)

        where value_n is the translation for the nth language in the
        ``languages`` list
        """
        query, _, columns = self._normalised_translations(languages)
        return query.values(*columns)

    def list_missing_translations(self, languages):
        """ as ``list_translations`` but restricted to rows where a translation
        is missing for at least one of the requested languages
        """
        query, aliases, columns = self._normalised_translations(languages)
        query = query.filter(or_(*(alias.value == NULL for alias in aliases)))
        return query.values(*columns)

    def suggest_translation(self, translatable, from_language, to_language):
        """Suggest a translation for a translatable, into `to_language`, given
        an existing translation in `from_language` based on other occurances
        of the same context being translated into a matching value for other
        message ids

        given the following translations table
            +----------------------------+------------+----------+----------+
            | context                    | message_id | language | value    |
            +----------------------------+------------+----------+----------+
            | taal:sa_field:model.column | [1]        | en       | Value    |
            | taal:sa_field:model.column | [1]        | fr       | Valeur   |
            | taal:sa_field:model.column | [2]        | en       | Value    |
            +----------------------------+------------+----------+----------+

        suggest_translation(
            TranslatableString(
                context="taal:sa_field:model.column",
                message_id=2),
            from_language='en',
            to_language='fr'
        )

        returns 'Valeur'

        If multiple suggestions are possible, the most frequently occuring one
        is returned
        """
        session = self.session
        model = self.model

        from_value = session.query(model.value).filter(
            model.context == translatable.context,
            model.message_id == translatable.message_id,
            model.language == from_language,
        ).scalar()

        if from_value is None:
            return None

        from_alias = aliased(model, name="from_language")
        to_alias = aliased(model, name="to_language")
        query = session.query(to_alias.value).outerjoin(
            from_alias,
            and_(
                from_alias.context == to_alias.context,
                from_alias.message_id == to_alias.message_id,
            )
        ).filter(
            from_alias.context == translatable.context,
            from_alias.language == from_language,
            from_alias.value == from_value,
            to_alias.language == to_language,
            to_alias.value != NULL,
        ).group_by(
            to_alias.value
        ).order_by(
            desc(func.count())
        )

        return query.limit(1).scalar()


class TranslationContextManager(object):
    """ Knows all available ``message_id``\s for a given context """

    __metaclass__ = ABCMeta

    @abstractproperty
    def context(self):
        """ String used to identify translations managed by this manager """

    @abstractmethod
    def list_message_ids(self):
        """ List of message ids for all objects managed by this manager """

    # consider including _create_translation or something similar
    # from tests/models.py


class TranslationManager(object):
    """ Collection of ``TranslationContextManager``\s """

    def __init__(self):
        self._registry = {}

    def register(self, context_manager):
        context = context_manager.context
        if context in self._registry:
            raise KeyError(
                "ContextManager with context '{}' already registered".format(
                    context)
            )
        self._registry[context] = context_manager

    def list_contexts_and_message_ids(self, **kwargs):
        for context, context_manager_cls in self._registry.items():
            context_manager = context_manager_cls(**kwargs)
            for message_id in context_manager.list_message_ids():
                yield (context, message_id)


translation_manager = TranslationManager()
