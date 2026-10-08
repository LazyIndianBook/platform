"""The words of the site: the publisher on the About page, the solutions' wording for either SOLUTIONS_REQUIRE_LOGIN
setting, no delivery promise outside the Shipping Policy, one vocabulary (Log in, Register) and a deletion page that
says what stays."""

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.urls import reverse

from accounts.factories import PASSWORD, UserFactory
from content.tests import make_paper
from shop import services
from shop.factories import ProductFactory, make_order

pytestmark = pytest.mark.django_db


def test_the_about_page_names_the_publisher_and_sends_to_the_contact_page(client):
    page = client.get(reverse("about")).text
    assert "ExamLeaf LLP" in page and "Bhaben Bhuyan" in page and f'href="{reverse("contact")}"' in page
    assert "Class XII" not in page and "three hours" in page  # every paper is 3 hours (checked on the import)


def test_the_words_about_registering_follow_the_setting(client, settings):
    book = make_paper().book
    settings.SOLUTIONS_REQUIRE_LOGIN = True
    assert "register once" in client.get(reverse("about")).text
    assert "for registered students" in client.get(book.get_absolute_url()).text
    settings.SOLUTIONS_REQUIRE_LOGIN = False
    assert "register once" not in client.get(reverse("about")).text
    assert "for registered students" not in client.get(book.get_absolute_url()).text


def test_no_delivery_time_is_promised_outside_the_shipping_policy(client, django_capture_on_commit_callbacks, settings):
    settings.SHOP_COD_ENABLED = True
    product = ProductFactory()
    page = client.get(product.get_absolute_url()).text
    assert reverse("shipping") in page and "working days" not in page
    order = make_order((product, 1), method="cod")
    with django_capture_on_commit_callbacks(execute=True):
        services.place_cod(order)
        services.deliver_order(services.ship_order(services.pack_order(order), "India Post", "EA1"))
    bodies = {m.subject.split("] ")[1]: m.body for m in mail.outbox}
    assert reverse("shipping") in bodies[f"Order {order.number} confirmed"]
    assert all("working days" not in body for body in bodies.values())


def test_the_site_says_log_in_and_register_everywhere(client):
    login, signup = client.get(reverse("account_login")).text, client.get(reverse("account_signup")).text
    assert "<h1>Log in</h1>" in login and ">Register</a>" in login and "Sign" not in login.split("<main>")[1]
    assert "<h1>Register</h1>" in signup and ">Log in</a>" in signup and "Sign" not in signup.split("<main>")[1]
    user = UserFactory()
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    response = client.post(reverse("account_login"), {"login": user.email, "password": PASSWORD}, follow=True)
    assert f"You are logged in as {user.email}." in response.text
    response = client.post(reverse("account_logout"), follow=True)
    assert "You have been logged out." in response.text
    assert mail.outbox == []


def test_emails_greet_from_examleaf_not_from_the_host_name(client):
    client.post(reverse("account_reset_password"), {"email": "nobody@example.com"}, HTTP_HOST="localhost")
    assert mail.outbox and "Hello from ExamLeaf!" in mail.outbox[0].body
    assert "Thank you for using ExamLeaf." in mail.outbox[0].body and "testserver" not in mail.outbox[0].subject


def test_the_deletion_page_says_that_orders_and_invoices_stay(client):
    client.force_login(UserFactory())
    page = client.get(reverse("account_delete"), follow=True).text
    assert "Orders and their invoices stay, as tax law requires" in page
