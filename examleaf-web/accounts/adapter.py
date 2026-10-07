from allauth.account.adapter import DefaultAccountAdapter
from allauth.core import context as allauth_context
from django.contrib.sites.shortcuts import get_current_site

from ops.tasks import queue_email


class AccountAdapter(DefaultAccountAdapter):
    def send_mail(self, template_prefix, email, context):
        """allauth's send_mail, with the sending done by a Celery task (rendering stays here: it needs the request)."""
        request = allauth_context.request
        context = {"request": request, "email": email, "current_site": get_current_site(request), **context}
        queue_email(self.render_mail(template_prefix, email, context))
