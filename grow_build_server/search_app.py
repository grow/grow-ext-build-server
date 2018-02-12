from google.appengine.api import memcache
from google.appengine.api import search
from google.appengine.ext import ndb
from protorpc import messages
from protorpc import remote
from protorpc.wsgi import service
from . import users
import bs4
import html2text
import logging
import os
import webapp2

INDEX = 'pages'
IS_DEV = os.getenv('SERVER_SOFTWARE', '').startswith('Dev')
NAMESPACE = os.getenv('CURRENT_VERSION_ID')


class FieldMessage(messages.Message):
    name = messages.StringField(1)
    value = messages.StringField(2)


class DocumentMessage(messages.Message):
    title = messages.StringField(1)
    locale = messages.StringField(2)
    language = messages.StringField(3)
    territory = messages.StringField(4)
    path = messages.StringField(5)
    snippet = messages.StringField(6)
    fields = messages.MessageField(FieldMessage, 7, repeated=True)


class QueryMessage(messages.Message):
    q = messages.StringField(1)
    limit = messages.IntegerField(2)
    cursor = messages.StringField(3)
    language = messages.StringField(4)


class SearchRequest(messages.Message):
    query = messages.MessageField(QueryMessage, 1)


class SearchResponse(messages.Message):
    documents = messages.MessageField(DocumentMessage, 1, repeated=True)
    cursor = messages.StringField(2)


class SearchSettings(ndb.Model):
    last_indexed_version = ndb.StringProperty()

    @classmethod
    def instance(cls):
        key = ndb.Key(cls.__name__, 'SearchSettings')
        ent = key.get()
        if ent is None:
            ent = cls(key=key)
            ent.put()
            logging.info('Created SearchSettings -> {}'.format(key))
        return ent


def _parse_locale_from_path(doc_id, locales):
    if not locales:
        return
    part = doc_id.lstrip('/')
    part = part.split('/', 1)[0] if '/' in part else part
    part = part.lower()
    locales = [locale.lower() for locale in locales]
    if part in locales:
        return part


def _parse_language_from_path(doc_id, locales):
    if not locales:
        return
    part = doc_id.lstrip('/')
    part = part.split('/', 1)[0] if '/' in part else part
    part = part.lower()
    locales = [locale.lower() for locale in locales]
    if part in locales:
        language = part.split('_')[0]
        if language == 'fil':
            language = 'tl'
        return language


def _get_search_items_from_soup(soup):
    parent_tags = soup.find_all(lambda tag: 'data-grow-search-item' in tag.attrs)
    search_items = []
    for parent in parent_tags:
        key_tags = parent.find_all(lambda tag: 'data-grow-search-item-key' in tag.attrs)
        keys_to_values = []

        doc_id = parent.get('data-grow-search-item-doc-id').replace(' ', '--')
        if doc_id:
            keys_to_values.append(('doc_id', doc_id))

        meta_description = parent.get('data-grow-search-item-meta-description')
        if meta_description:
            keys_to_values.append(('meta_description', meta_description))

        permalink_path = parent.get('data-grow-search-item-doc-permalink-path')
        if permalink_path:
            keys_to_values.append(('permalink_path', permalink_path))

        locale = parent.get('data-grow-search-item-locale')
        if locale:
            locale = locale.lower()
            keys_to_values.append(('locale', locale))

        for tag in key_tags:
            key = tag.get('data-grow-search-item-key')
            value = tag.get('data-grow-search-item-value')
            keys_to_values.append((key, value))
        search_items.append(keys_to_values)
    return search_items


def _get_fields_from_file(root, file_path, locales=None):
    doc_id = file_path[:-10] \
            if file_path.endswith('/index.html') else file_path
    doc_id = doc_id[len(root):]
    html = open(file_path).read()
    soup = bs4.BeautifulSoup(html, 'lxml')
    search_items = _get_search_items_from_soup(soup)
    fields_list = []
    if not search_items:
        fields = []
        fields.append(('doc_id', doc_id))
        fields.append(('language', _parse_language_from_path(doc_id, locales)))
        fields.append(('locale', _parse_locale_from_path(doc_id, locales)))
        # Max size, 500 is some buffer for the rest of the request.
        html = html.decode('utf-8')
        fields.append(('html', html2text.html2text(html)))
        fields.append(('title', soup.title.string.strip()))
        fields_list.append(fields)
    if search_items:
        # TODO: Make this support multiple keys with the same name.
        for item_fields in search_items:
            fields = []
            if 'doc_id' not in item_fields:
                fields.append(('doc_id', doc_id))
            fields.append(('language', _parse_language_from_path(doc_id, locales)))
            if 'locale' not in item_fields:
                fields.append(('locale', _parse_locale_from_path(doc_id, locales)))
            fields.append(('html', ''))  # TODO
            fields += item_fields
            fields_list.append(fields)
    return fields_list


def create_searchable_docs(root, file_path, locales=None):
    searchable_docs = []
    fields_list = _get_fields_from_file(root, file_path, locales=locales)
    for field_names_to_values in fields_list:
        parsed_fields = dict(field_names_to_values)
        try:
            fields = [
                search.AtomField(
                    name='locale',
                    value=parsed_fields['locale']),
                search.AtomField(
                    name='path',
                    value=(parsed_fields.get('permalink_path') or parsed_fields.get('doc_id')),
                    language=parsed_fields['language']),
                search.TextField(
                    name='title',
                    value=parsed_fields['title'],
                    language=parsed_fields['language']),
                search.HtmlField(
                    name='html',
                    value=parsed_fields['html'],
                    language=parsed_fields['language']),
            ]
            existing_fields = ['locale', 'path', 'title', 'html']
            for name, value in field_names_to_values:
                fields.append(search.TextField(name=name, value=value, language=parsed_fields['language']))
            doc = search.Document(doc_id=parsed_fields['doc_id'], fields=fields)
            searchable_docs.append(doc)
        except Exception as e:
            logging.error('Error indexing doc -> {}'.format(field_names_to_values))
            raise
    return searchable_docs


def collect_searchable_docs(root, locales=None):
    searchable_docs = []
    for dir_root, _, files in os.walk(root, topdown=True, followlinks=True):
        for filename in files:
            if not filename.endswith('.html'):
                continue
            path = os.path.join(dir_root, filename)
            docs = create_searchable_docs(root, path, locales=locales)
            for doc in docs:
                searchable_docs.append(doc)
    return searchable_docs


def index_searchable_docs(root, locales=None):
    searchable_docs = collect_searchable_docs(root, locales=locales)
    index = search.Index(INDEX, namespace=NAMESPACE)
    logging.info('Using FTS namespace -> {}'.format(NAMESPACE))
    for doc in searchable_docs:
        index.put(doc)
        logging.info('Indexed -> {}'.format(doc.doc_id))


def check_and_index_searchable_docs(root, locales, force=False):
    cache_key = 'grow-search-index:{}'.format(os.getenv('CURRENT_VERSION_ID', ''))
    has_indexed = memcache.get(cache_key)
    if has_indexed and not force:
        logging.info('Already indexed -> {}'.format(cache_key))
        return
    index_searchable_docs(root, locales=locales)
    memcache.set(cache_key, True)
    logging.info('Done indexing -> {}'.format(cache_key))


def _get_expression(doc, name):
    for expression in doc.expressions:
        if expression.name == name:
            return expression.value


def _get_field(doc, name):
    for field in doc.fields:
        if field.name == name:
            return field.value


def _get_all_fields(doc):
    messages = []
    for field in doc.fields:
        messages.append(FieldMessage(name=field.name, value=field.value))
    return messages


def clean_docs(user, docs):
    return [doc for doc in docs if user.can_read(doc.path)]


def execute_search(message):
    options = search.QueryOptions(snippeted_fields=['html'])
    if message.cursor:
        options.cursor = message.cursor
    if message.limit:
        optons.limit = message.limit
    query = search.Query(message.q, options=options)
    index = search.Index(INDEX, namespace=NAMESPACE)
    results = index.search(query)
    cursor = results.cursor
    docs = []
    if results.results:
        for doc in results.results:
            doc_message = DocumentMessage()
            doc_message.language = doc.language
            doc_message.locale = _get_field(doc, 'locale')
            doc_message.title = _get_field(doc, 'title')
            doc_message.path = _get_field(doc, 'path')
            doc_message.snippet = _get_expression(doc, 'html')
            doc_message.fields = _get_all_fields(doc)
            docs.append(doc_message)
    return docs, cursor


class IndexHandler(webapp2.RequestHandler):

    def get(self):
        root = self.app.config['root']
        locales = self.app.config['locales']
        force = self.request.get('force')
        check_and_index_searchable_docs(root, locales, force)


class SearchService(remote.Service):

    @remote.method(SearchRequest, SearchResponse)
    def search(self, request):
        if not request.query:
            raise remote.ApplicationError('Missing: query')
        user = users.User.get_from_environ()
        persistent_user = user and user.get_persistent()
        docs, cursor = execute_search(request.query)
        if not IS_DEV:
            docs = clean_docs(persistent_user, docs)
        resp = SearchResponse()
        if IS_DEV or persistent_user:
            resp.documents = docs
        resp.cursor = cursor
        return resp
