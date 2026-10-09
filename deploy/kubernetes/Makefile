# The Kubernetes packaging's tasks: the three images, the chart's checks, and the kind cluster that TESTING.md walks
# through. Run them from this directory (deploy/kubernetes/); `make` lists them.
TAG ?= $(shell git rev-parse --short HEAD)
# the chart's "registry" value: every image of the platform is <registry>/<name>:<tag>
REGISTRY ?= ghcr.io/lazyindianbook
DOMAIN ?= examleaf.in
# the chart's admin.host, and ERPNext's desk for the admin's links once it runs (https://erp.examleaf.in; empty: none)
ADMIN_HOST ?= admin.$(DOMAIN)
ERP_URL ?=
# the frontend's keys (empty: off). These, DOMAIN, ADMIN_HOST and ERP_URL are compiled into the two Next.js builds
# (their Dockerfiles' NEXT_PUBLIC_* arguments): change one, build again
RAZORPAY_KEY_ID ?=
TURNSTILE_SITE_KEY ?=
PUBLIC_MEDIA_DOMAIN ?=
CLUSTER ?= examleaf-test
NAMESPACE ?= examleaf
RELEASE ?= examleaf
CHART := examleaf-platform
# the values files of `make kind-install`: the laptop profile, or for TESTING.md's chaos run the HA profile on it:
#   make kind-install VALUES="-f examleaf-platform/values-kind.yaml -f examleaf-platform/values-ha.yaml -f examleaf-platform/values-kind-ha.yaml"
VALUES ?= -f $(CHART)/values-kind.yaml
WEB_IMAGE := $(REGISTRY)/examleaf-web:$(TAG)
FRONTEND_IMAGE := $(REGISTRY)/examleaf-frontend:$(TAG)
ADMIN_IMAGE := $(REGISTRY)/examleaf-admin:$(TAG)

# What a cluster needs before the chart (README.md, "Operators first"), each at a pinned release. Traefik goes into
# kube-system, as k3s runs its bundled one, with traefik-values.yaml and, on kind, the node's ports 80 and 443.
TRAEFIK_CHART_VERSION := 41.7.0
CERT_MANAGER := https://github.com/cert-manager/cert-manager/releases/download/v1.21.2/cert-manager.yaml
CNPG := https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.30/releases/cnpg-1.30.1.yaml
BARMAN_PLUGIN := https://github.com/cloudnative-pg/plugin-barman-cloud/releases/download/v0.15.1/manifest.yaml
# the Prometheus Operator's two CRDs that monitoring.enabled renders (kind has no Prometheus: TESTING.md)
PROMETHEUS_CRDS := https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/v0.94.1/example/prometheus-operator-crd

.DEFAULT_GOAL := help
.PHONY: help images push deps lint kind-up kind-secrets kind-buckets kind-monitoring-crds kind-load kind-install kind-down

help: ## list the tasks
	@grep -E '^[a-z-]+:.*## ' Makefile | sed 's/:.*## /\t/'

images: ## build examleaf-web, examleaf-frontend and examleaf-admin as REGISTRY/…:TAG (the git commit), for DOMAIN
	docker build --tag $(WEB_IMAGE) ../../examleaf-web
	docker build --tag $(FRONTEND_IMAGE) \
	  --build-arg NEXT_PUBLIC_SITE_URL=https://$(DOMAIN) \
	  --build-arg NEXT_PUBLIC_RAZORPAY_KEY_ID=$(RAZORPAY_KEY_ID) \
	  --build-arg NEXT_PUBLIC_TURNSTILE_SITE_KEY=$(TURNSTILE_SITE_KEY) \
	  --build-arg NEXT_PUBLIC_MEDIA_HOST=$(PUBLIC_MEDIA_DOMAIN) \
	  --build-arg NEXT_PUBLIC_RELEASE=$(TAG) \
	  ../../examleaf-frontend
	docker build --tag $(ADMIN_IMAGE) \
	  --build-arg NEXT_PUBLIC_SITE_URL=https://$(ADMIN_HOST) \
	  --build-arg NEXT_PUBLIC_WEBSITE_URL=https://$(DOMAIN) \
	  --build-arg NEXT_PUBLIC_ERP_URL=$(ERP_URL) \
	  ../../examleaf-admin

push: ## push the three images to REGISTRY (docker login ghcr.io first)
	docker push $(WEB_IMAGE)
	docker push $(FRONTEND_IMAGE)
	docker push $(ADMIN_IMAGE)

deps: ## fetch the chart's dependencies (the erpnext chart, switched off) into examleaf-platform/charts/
	helm dependency build $(CHART)

lint: deps ## helm lint and helm template, with the default values, values-kind.yaml and the HA profiles
	helm lint $(CHART)
	helm lint $(CHART) -f $(CHART)/values-kind.yaml
	helm lint $(CHART) -f $(CHART)/values-kind.yaml -f $(CHART)/values-ha.yaml -f $(CHART)/values-kind-ha.yaml
	helm template $(RELEASE) $(CHART) > /dev/null
	helm template $(RELEASE) $(CHART) -f $(CHART)/values-kind.yaml > /dev/null
	helm template $(RELEASE) $(CHART) -f $(CHART)/values-kind.yaml -f $(CHART)/values-ha.yaml -f $(CHART)/values-kind-ha.yaml > /dev/null
	helm template $(RELEASE) $(CHART) -f $(CHART)/values-ha.yaml --set config.MEDIA_BUCKET=m \
	  --set config.PUBLIC_MEDIA_BUCKET=p --set config.PUBLIC_MEDIA_DOMAIN=media.$(DOMAIN) > /dev/null

kind-up: ## the kind cluster with Traefik, cert-manager, CloudNativePG, its Barman Cloud plugin and kind-extras.yaml
	kind create cluster --name $(CLUSTER) --config kind-config.yaml
	helm upgrade --install traefik traefik --repo https://traefik.github.io/charts --version $(TRAEFIK_CHART_VERSION) \
	  --namespace kube-system -f traefik-values.yaml \
	  --set service.spec.type=ClusterIP --set ports.web.hostPort=80 --set ports.websecure.hostPort=443 \
	  --set updateStrategy.rollingUpdate.maxUnavailable=1 --set updateStrategy.rollingUpdate.maxSurge=0 \
	  --wait --timeout 5m
	kubectl apply -f $(CERT_MANAGER)
	kubectl apply --server-side -f $(CNPG)
	kubectl -n cert-manager rollout status deployment/cert-manager-webhook --timeout 300s
	kubectl apply -f $(BARMAN_PLUGIN)
	kubectl -n cnpg-system rollout status deployment/cnpg-controller-manager --timeout 300s
	kubectl -n cnpg-system rollout status deployment/barman-cloud --timeout 300s
	kubectl apply -f kind-extras.yaml

kind-secrets: ## the test cluster's Secrets, each made once with fresh random values (never written to a file)
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	kubectl -n s3 get secret rustfs-root > /dev/null 2>&1 || kubectl -n s3 create secret generic rustfs-root \
	  --from-literal=RUSTFS_ACCESS_KEY=$$(openssl rand -hex 10) --from-literal=RUSTFS_SECRET_KEY=$$(openssl rand -hex 20)
	KEY=$$(kubectl -n s3 get secret rustfs-root -o jsonpath='{.data.RUSTFS_ACCESS_KEY}' | base64 -d) \
	  && SECRET=$$(kubectl -n s3 get secret rustfs-root -o jsonpath='{.data.RUSTFS_SECRET_KEY}' | base64 -d) \
	  && { kubectl -n $(NAMESPACE) get secret $(RELEASE)-backup > /dev/null 2>&1 || kubectl -n $(NAMESPACE) create secret generic \
	         $(RELEASE)-backup --from-literal=AWS_ACCESS_KEY_ID=$$KEY --from-literal=AWS_SECRET_ACCESS_KEY=$$SECRET; } \
	  && { kubectl -n $(NAMESPACE) get secret $(RELEASE)-env > /dev/null 2>&1 || kubectl -n $(NAMESPACE) create secret generic \
	         $(RELEASE)-env --from-literal=SECRET_KEY=$$(openssl rand -hex 32) --from-literal=LEARN_CODE_SECRET=$$(openssl rand -hex 32) \
	         --from-literal=INTERNAL_API_TOKEN=$$(openssl rand -hex 24) --from-literal=INTEGRATION_KEYS=$$(openssl rand -base64 32 | tr '+/' '-_') \
	         --from-literal=S3_ACCESS_KEY_ID=$$KEY --from-literal=S3_SECRET_ACCESS_KEY=$$SECRET; }
	kubectl -n $(NAMESPACE) get secret $(RELEASE)-health-auth > /dev/null 2>&1 || kubectl -n $(NAMESPACE) create secret generic $(RELEASE)-health-auth \
	  --type=kubernetes.io/basic-auth --from-literal=username=monitor --from-literal=password=$$(openssl rand -hex 24)

kind-buckets: ## the media buckets of values-kind-ha.yaml in RustFS (once the web image is loaded)
	kubectl -n s3 run make-buckets --rm -i --restart=Never --quiet --image=$(WEB_IMAGE) --image-pull-policy=Never \
	  --overrides='{"spec": {"containers": [{"name": "make-buckets", "image": "$(WEB_IMAGE)", "imagePullPolicy": "Never", "envFrom": [{"secretRef": {"name": "rustfs-root"}}], "command": ["python", "-c", "import boto3, os; s3 = boto3.client(\"s3\", endpoint_url=\"http://rustfs:9000\", region_name=\"us-east-1\", aws_access_key_id=os.environ[\"RUSTFS_ACCESS_KEY\"], aws_secret_access_key=os.environ[\"RUSTFS_SECRET_KEY\"]); [s3.create_bucket(Bucket=b) for b in (\"examleaf-media\", \"examleaf-public\")]; print(sorted(b[\"Name\"] for b in s3.list_buckets()[\"Buckets\"]))"]}]}}'

kind-monitoring-crds: ## the PodMonitor and PrometheusRule CRDs, so that monitoring.enabled installs (no Prometheus)
	kubectl apply --server-side -f $(PROMETHEUS_CRDS)/monitoring.coreos.com_podmonitors.yaml \
	  -f $(PROMETHEUS_CRDS)/monitoring.coreos.com_prometheusrules.yaml

kind-load: ## copy the three images into the kind node (no registry)
	kind load docker-image $(WEB_IMAGE) $(FRONTEND_IMAGE) $(ADMIN_IMAGE) --name $(CLUSTER)

kind-install: deps ## helm install (or upgrade) the release into kind with VALUES (values-kind.yaml)
	helm upgrade --install $(RELEASE) $(CHART) --namespace $(NAMESPACE) --create-namespace \
	  $(VALUES) --set image.tag=$(TAG) --set frontend.image.tag=$(TAG) --set admin.image.tag=$(TAG) \
	  --wait --timeout 15m

kind-down: ## delete the kind cluster, then the dangling images
	kind delete cluster --name $(CLUSTER)
	docker image prune -f
