from google.appengine.api import users as api_users
from google.appengine.ext import ndb
from google.appengine.ext.webapp import mail_handlers
from google.appengine.api import app_identity
import datetime
import users
import emailer
import google_sheets
import jinja2
import logging
import os
import webapp2


APPID = app_identity.get_application_id()
SERVICE_ACCOUNT_EMAIL = '{}@appspot.gserviceaccount.com'.format(APPID)


def get_build_timestamp():
    version_id = os.getenv('CURRENT_VERSION_ID').split('.')[-1]
    if not version_id:
      return
    timestamp = long(version_id) / pow(2, 28)
    return datetime.datetime.fromtimestamp(timestamp).strftime('%d/%m/%y %X')


class SeenAccessRequest(ndb.Model):
    email = ndb.StringProperty()
    timestamp = ndb.StringProperty()

    @classmethod
    def get(cls, timestamp, email):
        key = ndb.Key('SeenAccessRequest', '{}:{}'.format(timestamp, email))
        return key.get()

    @classmethod
    def save(cls, timestamp, email):
        key = ndb.Key('SeenAccessRequest', '{}:{}'.format(timestamp, email))
        ent = cls(key=key, timestamp=timestamp, email=email)
        ent.put()
        return ent


def get_access_requests(access_request_sheet_id, access_request_gid):
    requests = google_sheets.get_sheet(
            access_request_sheet_id, gid=access_request_gid,
            use_cache=False)
    new_user_access_requests = []
    for row in requests:
        email = row['Email address']
        # Sometimes emails are misformatted as a list. Reduce the list to the
        # first email address.
        if ',' in email:
            email = email.split(',')[0]
        email = email.strip()
        seen_access_request = \
                SeenAccessRequest.get(row['Timestamp'], email)
        if seen_access_request is None:
            logging.info('Found access request from -> {}'.format(email))
            new_user_access_requests.append({
                'email': email,
                'form': row,
            })
    return new_user_access_requests


def process_access_requests(config):
    access_request_sheet_id = \
            config['access_requests']['form_response_sheet_id']
    access_request_gid = \
            config['access_requests'].get('form_response_gid')
    acl_sheet_id = google_sheets.Settings.instance().sheet_id
    new_user_access_requests = get_access_requests(
            access_request_sheet_id=access_request_sheet_id,
            access_request_gid=access_request_gid)
    for req in new_user_access_requests:
        send_email_to_admins(
                req,
                email_config=config['access_requests']['emails'])
        if req['form']['Timestamp'] and req['email']:
            SeenAccessRequest.save(req['form']['Timestamp'], req['email'])


def send_email_to_existing_user(email, email_config, kwargs=None):
    title =  '[{}] Your access has been updated'
    subject = title.format(email_config['title'])
    params = {
        'email': email,
        'email_config': email_config
    }
    if kwargs:
        params.update(kwargs)
    emailer_ent = emailer.Emailer()
    emailer_ent.send(
        to=email,
        subject=subject,
        template_path='email_to_existing_user.html',
        kwargs=params)
    logging.info('Emailed existing user -> {}'.format(email))


def send_email_to_new_user(email, email_config):
    title =  '[{}] Your access request has been approved'
    subject = title.format(email_config['title'])
    emailer_ent = emailer.Emailer()
    emailer_ent.send(
        to=email,
        subject=subject,
        template_path='email_to_new_user.html',
        kwargs={'email': email, 'email_config': email_config})
    logging.info('Emailed new user -> {}'.format(email))


def send_email_to_admins(req, email_config):
    # Normalize encoding for rendering email template.
    if 'form' in req:
        for i, question in enumerate(req['form']):
            answer = question.answer
            if isinstance(answer, unicode):
                answer = answer.encode('utf-8')
            if answer:
                req['form'][i].answer = answer.decode('utf-8')
    admin_emails = get_admins(notify_only=True)
    if not admin_emails:
        logging.error('No admins to email.')
        return
    emailer_ent = emailer.Emailer()
    emailer_ent.send(
        to=admin_emails,
        subject='[{}] Request for access from {}'.format(
            email_config['title'], req['email']),
        template_path='email_to_admins.html',
        kwargs={'req': req, 'email_config': email_config})
    logging.info('Emailed admins -> {}'.format(', '.join(admin_emails)))


def add_user_to_acl(new_user_email):
    logging.info('Adding user to ACL -> {}'.format(new_user_email))
    instance = google_sheets.Settings.instance()
    sheet_id = instance.sheet_id
    gid = instance.sheet_gid_global
    rows = [[new_user_email]]
    google_sheets.append_rows(sheet_id, gid, rows)


def get_admins(notify_only=False):
    instance = google_sheets.Settings.instance()
    sheet_id = instance.sheet_id
    admins_gid = instance.sheet_gid_admins
    admins = google_sheets.get_sheet(sheet_id, gid=admins_gid, use_cache=False)
    if notify_only:
        return [row.get('email') for row in admins if row.get('notify')]
    return [row.get('email') for row in admins]


def jinja2_env():
    path = os.path.join(os.path.dirname(__file__), 'templates')
    loader = jinja2.FileSystemLoader([path])
    return jinja2.Environment(loader=loader, autoescape=True, trim_blocks=True)


class ApproveAccessRequestHandler(webapp2.RequestHandler):

    def get(self, new_user_email):
        admins = get_admins()
        user = api_users.get_current_user()
        if not user:
            url = self.app.config['access_requests']['sign_in_path']
            self.redirect(url)
            return
        # Only admins can approve access.
        if user.email() not in admins:
            webapp2.abort(403)
            return
        acl_sheet_id = google_sheets.Settings.instance().sheet_id
        url = google_sheets.get_spreadsheet_url(acl_sheet_id)
        email_config = self.app.config['access_requests']['emails']
        add_user_to_acl(new_user_email)
        send_email_to_new_user(new_user_email, email_config)
        template = jinja2_env().get_template('admin_access_request_approved.html')
        html = template.render({
            'email': new_user_email,
            'email_config': email_config,
            'spreadsheet_url': url,
        })
        self.response.out.write(html)


class FormResponseHandler(mail_handlers.InboundMailHandler):

    def receive(self, message):
        process_access_requests()


class ManageAccessHandler(webapp2.RequestHandler):

    def get(self):
        # TODO: Move to a decorator.
        user = api_users.get_current_user()
        if not user:
            url = api_users.create_login_url(self.request.path)
            self.redirect(url)
            return
        is_admin = api_users.is_current_user_admin()
        if not is_admin:
            webapp2.abort(403)
            return
        # TODO: Move to a decorator (above).
        template = jinja2_env().get_template('admin_manage_access.html')
        email_config = self.app.config['access_requests']['emails']
        html = template.render({
            'title': email_config.title,
            'email_config': email_config,
        })
        self.response.out.write(html)


class ManageUserHandler(webapp2.RequestHandler):

    def get(self, email):
        # TODO: Move to a decorator.
        user = api_users.get_current_user()
        if not user:
            url = api_users.create_login_url(self.request.path)
            self.redirect(url)
            return
        is_admin = api_users.is_current_user_admin()
        if not is_admin:
            webapp2.abort(403)
            return
        # TODO: Move to a decorator (above).
        template = jinja2_env().get_template('admin_manage_user.html')
        user_to_edit = users.PersistentUser.get(email)
        html = template.render({
            'user': user_to_edit,
            'folders': users.list_folder_messages(),
        })
        self.response.out.write(html)


class ManageUsersHandler(webapp2.RequestHandler):

    def get(self):
        # TODO: Move to a decorator.
        user = api_users.get_current_user()
        if not user:
            url = api_users.create_login_url(self.request.path)
            self.redirect(url)
            return
        is_admin = api_users.is_current_user_admin()
        if not is_admin:
            webapp2.abort(403)
            return
        # TODO: Move to a decorator (above).
        template = jinja2_env().get_template('admin_manage_users.html')
        html = template.render({
            'service_account_email': SERVICE_ACCOUNT_EMAIL,
            'build_server_config': self.app.config,
            'timestamp': get_build_timestamp(),
            'folders': users.list_folder_messages(),
        })
        self.response.out.write(html)


class ProcessHandler(webapp2.RequestHandler):

    def get(self):
        process_access_requests(self.app.config)


class DownloadCsvHandler(webapp2.RequestHandler):

    def get(self):
        content = users.PersistentUser.to_csv()
        filename = 'users_{}'.format(datetime.datetime.now())
        filename = filename.replace(' ', '-')
        header = 'inline; filename="{}.csv"'.format(filename)
        self.response.headers['Content-Type'] = 'text/csv'
        self.response.headers['Content-Disposition'] = header
        self.response.out.write(content)


class ImportFromSheetsHandler(webapp2.RequestHandler):

    def get(self):
        users.PersistentUser.import_from_sheets()
