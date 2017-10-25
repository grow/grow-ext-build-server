from google.appengine.api import memcache
from google.appengine.api import search
from google.appengine.ext import ndb
from protorpc import messages
from protorpc import remote
from protorpc.wsgi import service
import bs4
import html2text
import logging
import os
import webapp2

INDEX = 'pages'
NAMESPACE = os.getenv('CURRENT_VERSION_ID')


class DocumentMessage(messages.Message):
    title = messages.StringField(1)
    locale = messages.StringField(2)
    language = messages.StringField(3)
    territory = messages.StringField(4)
    path = messages.StringField(5)
    snippet = messages.StringField(6)


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


def _get_fields_from_file(root, file_path, locales=None):
    doc_id = file_path[:-10] \
            if file_path.endswith('/index.html') else file_path
    doc_id = doc_id[len(root):]
    html = open(file_path).read()
    soup = bs4.BeautifulSoup(html, 'lxml')
    fields = {}
    fields['doc_id'] = doc_id
    fields['language'] = _parse_language_from_path(doc_id, locales)
    fields['locale'] = _parse_locale_from_path(doc_id, locales)
    # Max size, 500 is some buffer for the rest of the request.
    fields['html'] = html2text.html2text(html)
    fields['title'] = soup.title.string.strip()
    return fields


def create_searchable_doc(root, file_path, locales=None):
    parsed = _get_fields_from_file(root, file_path, locales=locales)
    try:
        fields = [
            search.AtomField(
                name='locale',
                value=parsed['locale']),
            search.AtomField(
                name='path',
                value=parsed['doc_id'],
                language=parsed['language']),
            search.TextField(
                name='title',
                value=parsed['title'],
                language=parsed['language']),
            search.HtmlField(
                name='html',
                value=parsed['html'],
                language=parsed['language']),
        ]
        doc = search.Document(doc_id=parsed['doc_id'], fields=fields)
        return doc
    except Exception as e:
        logging.error('Error indexing doc -> {}'.format(parsed['doc_id']))
        raise


def collect_searchable_docs(root, locales=None):
    searchable_docs = []
    for dir_root, _, files in os.walk(root, topdown=True, followlinks=True):
        for filename in files:
            if not filename.endswith('.html'):
                continue
            path = os.path.join(dir_root, filename)
            doc = create_searchable_doc(root, path, locales=locales)
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
        docs, cursor = execute_search(request.query)
        resp = SearchResponse()
        resp.documents = docs
        resp.cursor = cursor
        return resp
