from google.appengine.api import users
from google.appengine.ext import ndb
from google.appengine.ext.webapp import mail_handlers
import emailer
import google_sheets
import jinja2
import logging
import os
import webapp2


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
            access_request_sheet_id, gid=access_request_gid)
    new_user_access_requests = []
    for row in requests:
        email = row['Email address']
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
    admin_emails = get_admins(notify_only=True)
    emailer_ent = emailer.Emailer()
    emailer_ent.send(
        to=admin_emails,
        subject='[{}] Request for access from {}'.format(
            email_config['title'], req['email']),
        template_path='email_to_admins.html',
        kwargs={'req': req, 'email_config': email_config})
    logging.info('Emailed admin -> {}'.format(email))


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
    admins = google_sheets.get_sheet(sheet_id, gid=admins_gid)
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
        user = users.get_current_user()
        # Only admins can approve access.
        if user.email() not in admins:
            webapp2.abort(403)
            return
        acl_sheet_id = google_sheets.Settings.instance().sheet_id
        url = google_sheets.get_spreadsheet_url(acl_sheet_id)
        email_config = self.app.config['access_requests']['emails']
        add_user_to_acl(new_user_email)
        send_email_to_new_user(new_user_email, email_config)
        template = jinja2_env().get_template('base.html')
        html = template.render({
            'email': new_user_email,
            'email_config': email_config,
            'spreadsheet_url': url,
        })
        self.response.out.write(html)


class ProcessHandler(webapp2.RequestHandler):

    def get(self):
        process_access_requests(self.app.config)


class FormResponseHandler(mail_handlers.InboundMailHandler):

    def receive(self, message):
        process_access_requests()
