from google.appengine.ext import vendor
vendor.add('extensions')

from google.appengine.api import mail
import jinja2
import os
import premailer


_appid = os.getenv('APPLICATION_ID').replace('s~', '')
EMAIL_SENDER = 'noreply@{}.appspotmail.com'.format(_appid)


class Emailer(object):

    def __init__(self, sender=None):
        self.sender = sender or EMAIL_SENDER

    def send(self, to, subject, template_path, kwargs=None):
        html = self._render(template_path, kwargs=kwargs)
        self._send(subject, to, html)

    def _render(self, template_path, kwargs=None):
        params = {}
        if kwargs:
            params.update(kwargs)
        template = self.env.get_template(template_path)
        html = template.render(params)
        return premailer.transform(html)

    def _send(self, subject, to, html):
        message = mail.EmailMessage(sender=self.sender, subject=subject)
        message.to = to
        message.html = html
        message.send()

    @property
    def env(self):
        path = os.path.join(os.path.dirname(__file__), 'templates')
        loader = jinja2.FileSystemLoader([path])
        return jinja2.Environment(loader=loader, autoescape=True, trim_blocks=True)
