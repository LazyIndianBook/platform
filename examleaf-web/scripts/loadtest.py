"""The load test of RESILIENCE.md, with nothing but the standard library: concurrent connections against gunicorn for
a while, the catalogue, a paper and its solutions, guest carts and the config beside two slow dependencies (Razorpay
and MSG91, both stubbed to answer after 10 seconds), with the latencies and the processes' memory reported.

    python scripts/loadtest.py stub                    # the slow Razorpay and MSG91 (port 18799), in its own terminal
    python scripts/loadtest.py seed > /tmp/plan.json   # against the database of DATABASE_URL: users, guest orders
    gunicorn --config gunicorn.conf.py 'scripts.loadtest:application()'   # the site, its calls sent to the stub
    python scripts/loadtest.py run --plan /tmp/plan.json --seconds 60 --connections 50 --slow-payment 10 --slow-sms 5

RESILIENCE.md "Load test" has the settings used (production-like: DEBUG=0, PostgreSQL, the cache Redis, the queue's
Redis down so that an SMS is sent inside the request) and the numbers."""

import argparse
import http.client
import io
import json
import os
import random
import statistics
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STUB = os.environ.get("LOADTEST_STUB", "http://127.0.0.1:18799")


def application():
    """gunicorn's app factory ('scripts.loadtest:application()'): the site, with Razorpay and MSG91 at the stub."""
    import razorpay

    razorpay.Client.DEFAULTS["base_url"] = f"{STUB}/v1"
    from examleaf.wsgi import application as site
    from ops import sms

    sms.MSG91 = f"{STUB}/api/v5/"
    return site


class Slow(BaseHTTPRequestHandler):
    """Razorpay (/v1/…) answers a server error after SLEEP seconds, MSG91 (/api/v5/…) a success: a provider that is
    up but slow. A client that gave up meanwhile is not written to."""

    SLEEP = 10.0

    def answer(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        time.sleep(self.SLEEP)
        razorpay = self.path.startswith("/v1")
        status = 500 if razorpay else 200
        body = {"error": {"code": "SERVER_ERROR", "description": "stub"}} if razorpay else {"type": "success"}
        try:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            pass

    do_GET = do_POST = answer

    def log_message(self, *args):
        pass


def stub(port):
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer(("127.0.0.1", port), Slow).serve_forever()


def seed(phones, orders):
    """Users with confirmed mobile numbers (for log-in codes by SMS) and guest orders awaiting payment (Razorpay), on
    top of seed_shop and the fixture papers. Prints the plan the run reads."""
    import django

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # examleaf-web, as manage.py has it
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "examleaf.settings")
    django.setup()
    from allauth.account.models import EmailAddress
    from django.core.management import call_command

    from accounts.models import User
    from content.models import Paper
    from shop.cart import set_quantity
    from shop.models import Cart, Payment, Product
    from shop.services import create_order

    quiet = {"stdout": io.StringIO(), "verbosity": 0}  # stdout is the plan's
    call_command("import_papers", "--all", "--fixtures", **quiet)
    call_command("seed_shop", "--stock", "100000", **quiet)  # after the papers: a product names its book
    numbers = [f"+91986{index:07d}" for index in range(phones)]
    for number in numbers:
        user, _ = User.objects.get_or_create(email=f"{number[1:]}@loadtest.invalid")
        user.login_phone, user.login_phone_verified = number, True
        user.save()
        EmailAddress.objects.get_or_create(user=user, email=user.email, defaults={"verified": True, "primary": True})
    books = list(Product.objects.filter(is_active=True, stock__gt=0).exclude(kind="digital").order_by("pk"))
    address = {"name": "Load Test", "phone": "+919864012345", "line1": "House 4, Zoo Road", "line2": ""}
    address |= {"city": "Guwahati", "district": "Kamrup Metro", "state": "AS", "pin": "781001"}
    tokens = []
    for _ in range(orders):
        cart = Cart.objects.create()
        set_quantity(cart, books[0], 1)
        order = create_order(cart, user=None, email="guest@loadtest.invalid", address=address, method="razorpay")
        tokens.append(order.token)
    assert not Payment.objects.filter(order__token__in=tokens).exclude(razorpay_order_id=None).exists()
    papers = list(Paper.objects.filter(is_published=True).values_list("code", flat=True)[:20])
    plan = {"phones": numbers, "orders": tokens, "products": [book.slug for book in books], "papers": papers}
    json.dump(plan, sys.stdout)


class Client:
    """One connection's loop: a request at a time, as a proxy's connection or a phone does."""

    def __init__(self, base, token, keepalive):
        self.host, self.port = base.removeprefix("http://").split(":")
        self.token, self.keepalive, self.connection = token, keepalive, None
        self.cart = None

    def send(self, method, path, body=None, headers=None):
        address = f"10.{random.randrange(256)}.{random.randrange(256)}.{random.randrange(1, 255)}"
        headers = {
            "Host": "localhost",
            "Accept": "application/json",
            "X-Internal-Token": self.token,  # the frontend's: each request counts for its own visitor's address
            "X-Forwarded-For": address,
            "Connection": "keep-alive" if self.keepalive else "close",
            **(headers or {}),
        }
        data = json.dumps(body).encode() if body is not None else None
        if data is not None:
            headers["Content-Type"] = "application/json"
        started = time.monotonic()
        try:
            if self.connection is None:
                self.connection = http.client.HTTPConnection(self.host, int(self.port), timeout=120)
            self.connection.request(method, path, body=data, headers=headers)
            response = self.connection.getresponse()
            payload = response.read()
            status = response.status
        except (OSError, http.client.HTTPException) as error:
            payload, status = str(error).encode(), 0
            self.close()
        if not self.keepalive:
            self.close()
        return status, time.monotonic() - started, payload

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None


def fast_request(client, plan):
    """A visitor's page: the catalogue, a book, a paper and its solutions, their guest cart, the site's config."""
    if client.cart is None:
        status, seconds, payload = client.send("POST", "/api/v1/cart/", {})
        client.cart = json.loads(payload)["token"] if status == 201 else ""
        return "cart start", status, seconds
    name, method, path, body = random.choice(
        [
            ("products", "GET", "/api/v1/products/", None),
            ("product", "GET", f"/api/v1/products/{random.choice(plan['products'])}/", None),
            ("books", "GET", "/api/v1/books/", None),
            ("paper", "GET", f"/api/v1/papers/{random.choice(plan['papers'])}/", None),
            ("solutions", "GET", f"/api/v1/papers/{random.choice(plan['papers'])}/solutions/", None),
            ("config", "GET", "/api/v1/config/", None),
            ("cart", "GET", "/api/v1/cart/", None),
            ("cart add", "POST", "/api/v1/cart/items/", {"product": random.choice(plan["products"]), "quantity": 1}),
        ]
    )
    status, seconds, _ = client.send(method, path, body, {"X-Cart-Token": client.cart} if client.cart else None)
    return name, status, seconds


def payment_request(client, plan):
    """Pay a guest order: Razorpay's order is made in the request (shop.payments), and Razorpay is slow."""
    status, seconds, _ = client.send("POST", f"/api/v1/orders/t/{random.choice(plan['orders'])}/payment/", {})
    return "payment (Razorpay)", status, seconds


def sms_request(client, plan):
    """A log-in code by SMS: with the queue down, MSG91 is called in the request (ops.sms.queue_sms), and is slow."""
    status, seconds, _ = client.send("POST", "/api/v1/auth/phone/code/", {"phone": random.choice(plan["phones"])})
    return "log-in code (MSG91)", status, seconds


def memory(pattern):
    """The resident memory (MB) of each process whose command line matches `pattern` (gunicorn's master and workers)."""
    pids = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True).stdout.split()
    sizes = {}
    for pid in pids:
        out = subprocess.run(["ps", "-o", "rss=,comm=", "-p", pid], capture_output=True, text=True).stdout.split()
        if out and not out[1].endswith("sh"):  # not the shell that started gunicorn
            sizes[pid] = int(out[0]) // 1024
    return sizes


def percentile(values, share):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))] if ordered else 0


def run(args):
    plan = json.loads(Path(args.plan).read_text())
    kinds = [payment_request] * args.slow_payment + [sms_request] * args.slow_sms
    kinds += [fast_request] * (args.connections - len(kinds))
    results, stop, lock = [], time.monotonic() + args.seconds, threading.Lock()

    def loop(kind):
        client = Client(args.base, args.token, args.keepalive)
        while time.monotonic() < stop:
            started = time.monotonic()
            name, status, seconds = kind(client, plan)
            with lock:
                results.append((name, status, seconds, started))
        client.close()

    threads = [threading.Thread(target=loop, args=(kind,), daemon=True) for kind in kinds]
    samples, started = [], time.monotonic()
    for thread in threads:
        thread.start()
    while any(thread.is_alive() for thread in threads):
        samples.append((round(time.monotonic() - started), memory(args.processes)))
        for thread in threads:
            thread.join(timeout=5 / len(threads))
        time.sleep(max(0, 5 - (time.monotonic() - started) % 5))
    report = {"settings": vars(args), "endpoints": {}, "memory_mb": samples}
    for name in sorted({row[0] for row in results}):
        rows = [row for row in results if row[0] == name]
        latencies = [row[2] * 1000 for row in rows]
        statuses = {}
        for row in rows:
            statuses[row[1]] = statuses.get(row[1], 0) + 1
        report["endpoints"][name] = {
            "requests": len(rows),
            "per_second": round(len(rows) / args.seconds, 1),
            "statuses": statuses,
            "p50_ms": round(statistics.median(latencies)),
            "p95_ms": round(percentile(latencies, 0.95)),
            "p99_ms": round(percentile(latencies, 0.99)),
            "max_ms": round(max(latencies)),
        }
    fast = [row[2] * 1000 for row in results if row[0] not in ("payment (Razorpay)", "log-in code (MSG91)")]
    report["fast_overall"] = {
        "requests": len(fast),
        "per_second": round(len(fast) / args.seconds, 1),
        "p50_ms": round(statistics.median(fast)) if fast else 0,
        "p95_ms": round(percentile(fast, 0.95)),
        "p99_ms": round(percentile(fast, 0.99)),
        "max_ms": round(max(fast)) if fast else 0,
        "over_1s": sum(value > 1000 for value in fast),
    }
    print(json.dumps(report, indent=1))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("stub").add_argument("--port", type=int, default=18799)
    seeding = commands.add_parser("seed")
    seeding.add_argument("--phones", type=int, default=300)
    seeding.add_argument("--orders", type=int, default=200)
    running = commands.add_parser("run")
    running.add_argument("--plan", required=True)
    running.add_argument("--base", default="http://127.0.0.1:18800")
    running.add_argument("--token", default=os.environ.get("INTERNAL_API_TOKEN", ""))
    running.add_argument("--seconds", type=int, default=60)
    running.add_argument("--connections", type=int, default=50)
    running.add_argument("--slow-payment", type=int, default=0, help="connections paying (Razorpay, slow)")
    running.add_argument("--slow-sms", type=int, default=0, help="connections asking SMS codes (MSG91, slow)")
    running.add_argument("--keepalive", action="store_true", help="one connection per client (default: one each)")
    running.add_argument("--processes", default="loadtest:application", help="pgrep pattern of gunicorn's processes")
    args = parser.parse_args()
    if args.command == "stub":
        stub(args.port)
    elif args.command == "seed":
        seed(args.phones, args.orders)
    else:
        run(args)


if __name__ == "__main__":
    main()
