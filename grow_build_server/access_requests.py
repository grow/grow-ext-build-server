from google.appengine.api import users
from google.appengine.ext.webapp import mail_handlers
import emailer
import google_sheets
import webapp2


def get_access_requests(
        access_request_sheet_id, access_request_gid,
        acl_sheet_id, acl_sheet_gid=None):
    results = google_sheets.get_sheet(
            access_request_sheet_id, gid=access_request_gid)
    acl = google_sheets.get_sheet(
            acl_sheet_id, gid=acl_sheet_gid)
    existing_users = [row.get('email', '').strip() for row in acl if row]
    new_user_access_requests = []
    for row in acl:
        email = row.get('email', '')
        if email and email not in new_users:
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
            access_request_gid=access_request_gid,
            acl_sheet_id=acl_sheet_id)
    for req in new_user_access_requests:
        send_email_to_admins(
                new_user_access_request=req,
                email_config=config['access_requests']['emails'])


def send_email_to_new_user(req, email_config):
    subject = '[{}] Your access request has been approved'.format(email_config['title'])
    admin_emails = []
    emailer_ent = emailer.Emailer()
    emailer_ent.send(
        to=req['email'],
        subject=subject,
        template_path='email_to_new_user.html',
        kwargs={'req': req})


def send_email_to_admins(req, email_config):
    admin_emails = []
    emailer_ent = emailer.Emailer()
    emailer_ent.send(
        to=admin_emails,
        subject='[{}] Request for access -> {}'.format(
            email_config['title'], req['email']),
        template_path='email_to_admins.html')


def add_user_to_acl(new_user_email):
    instance = google_sheets.Settings.instance()
    sheet_id = isntance.sheet_id
    pass


class FormResponseHandler(mail_handlers.InboundMailHandler):

    def receive(self, message):
        process_access_requests()


def get_admins():
    instance = google_sheets.Settings.instance()
    sheet_id = isntance.sheet_id
    admins_gid = instance.admins_gid
    admins = google_sheets.get_sheet(sheet_id, admins_gid)
    return [row.get('email') for row in admins]


class ApproveAccessRequestHandler(webapp2.RequestHandler):

    def get(self, new_uaser_email):
        user = users.get_current_user()
        # Only admins can approve access.
        if user.email not in admins:
            webapp2.abort(403)
            return
        add_user_to_acl(new_user_email)
        send_email_to_new_user(
                new_user_email,
                self.app.config['access_requests']['emails'])
