from google.appengine.ext import vendor
vendor.add('extensions')

from google.appengine.api import mail
from google.appengine.ext.webapp import template
import os
import premailer


class Emailer(object):

    def __init__(self, sender):
        self.sender = sender

    def send(self, to, subject, template_path, content=None, kwargs=None):
        html = self._render(template_path, content=content, kwargs=kwargs)
        self._send(subject, to, html)

    def _render(self, template_path, content=None, kwargs=None):
        params = {
            'base_url': None,
            'footer': None,
            'content': content,
            'logo_url': None,
            'title': None,
        }
        if kwargs:
            params.update(kwargs)
        path = os.path.join(os.path.dirname(__file__), 'templates', template_path)
        html = template.render(path, params)
        return premailer.transform(html)

    def _send(self, subject, to, html):
        message = mail.EmailMessage(sender=self.sender, subject=subject)
        message.to = to
        message.html = html
        message.send()
